#!/usr/bin/env python3
"""
Standalone PaddleOCR-VL worker script.

Must be executed by a Python 3.9–3.13 interpreter that has PaddlePaddle and
paddleocr[doc-parser] installed.  The main application (Python 3.14) calls
this script as a subprocess.

Protocol
--------
Invocation:
    <python> paddle_vl_worker.py <image_path> [device]

    device  — PaddlePaddle device string passed to PaddleOCRVL(device=...).
              Examples: gpu  gpu:0  cpu   (default: gpu)

Stdout (always a single JSON line):
    Success → {"ok": true, "markdown": "<full document text>", "json_result": <object or null>}
    Failure → {"ok": false, "error": "<error message>"}

    When json_result is non-null it contains the structured EIR fields extracted
    via VQA mode and should be preferred over regex parsing of the markdown.

Exit code:
    0  on success
    1  on any error
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile


# ── Structured extraction prompt (VQA / chat mode) ────────────────────────────

_EXTRACTION_QUERY = """
You are an expert document parser for Equipment Interchange Receipts (EIR) issued by container
terminals. The document may contain English and/or Arabic text, rotated labels, stamps, and
handwritten annotations.

Extract ONLY the 7 fields listed below and return ONLY a valid JSON object — no extra text,
no markdown fences, no explanation.

{
  "container_number":      "<4 uppercase letters + 7 digits e.g. MSCU1234567, or null>",
  "seal_number":           "<seal/lock number string, or null>",
  "container_size":        "<one of: 20 | 40 | 45 | 40HC | 45HC | OTHER, or null>",
  "vehicle_number":        "<full truck/vehicle plate number, or null>",
  "haulier":               "<haulier or trucking company name, or null>",
  "receipt_date":          "<ISO 8601 YYYY-MM-DDTHH:MM:SS, or null>",
  "gross_weight":          {"value": <number or null>, "unit": "<KG | MT | null>"},
  "extraction_confidence": <float 0.0-1.0>
}

Rules:
- Container number: 4 letters + 7 digits (includes check digit), e.g. MSCU1234567.
- Container size: extract the number only from "SIZE / TYPE" field (e.g. "20 GP" → "20").
- Receipt date: label is "DATE OF ISSUE", typically DD-MM-YYYY HH:MM → convert to ISO 8601.
- Gross weight: label is "WEIGHT"; if shown as "24420/VGM" then value=24420, unit="KG".
- Normalize Arabic-Indic numerals (٠١٢٣٤٥٦٧٨٩) to Western numerals.
- Output exactly the JSON object above — do NOT add extra keys.
""".strip()


def main() -> int:
    if len(sys.argv) < 2:
        _fail("Usage: paddle_vl_worker.py <image_path> [device]")
        return 1

    image_path = sys.argv[1]
    device = sys.argv[2] if len(sys.argv) >= 3 else "gpu"

    if not os.path.isfile(image_path):
        _fail(f"File not found: {image_path!r}")
        return 1

    try:
        from paddleocr import PaddleOCRVL  # type: ignore[import]
    except ImportError as exc:
        _fail(
            f"paddleocr is not installed in this interpreter ({sys.executable}): {exc}\n"
            "GPU (Blackwell/sm_120): pip install paddlepaddle-gpu==3.2.1 "
            "-i https://www.paddlepaddle.org.cn/packages/stable/cu129/ "
            "&& pip install 'paddleocr[doc-parser]'\n"
            "CPU:                   pip install paddlepaddle 'paddleocr[doc-parser]'"
        )
        return 1

    try:
        pipeline = PaddleOCRVL(device=device)

        # Release any cached-but-unused GPU tensors accumulated during model
        # initialisation before running inference.  On ≤8 GB cards this is the
        # difference between a successful bfloat16→float32 cast and an OOM.
        if "gpu" in device.lower():
            try:
                import paddle  # type: ignore[import]
                paddle.device.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass

        # ── Attempt 1: VQA mode with structured JSON prompt ──────────────────
        # PaddleOCR 3.x VL pipelines support predict(input=..., query=...) for
        # document VQA.  This gives far better structured output than OCR markdown.
        json_result, markdown = _run_with_vqa(pipeline, image_path)

        # ── Attempt 2: plain OCR fallback ────────────────────────────────────
        if markdown is None:
            output = pipeline.predict(input=image_path)
            markdown = _collect_markdown(output)

    except Exception as exc:  # noqa: BLE001
        _fail(f"{type(exc).__name__}: {exc}")
        return 1
    finally:
        _free_memory(device)

    _ok(markdown=markdown or "", json_result=json_result)
    return 0


# ── VQA attempt ───────────────────────────────────────────────────────────────

def _run_with_vqa(pipeline, image_path: str) -> tuple[dict | None, str | None]:
    """
    Try to call predict() in VQA mode with the JSON extraction prompt.

    Returns (json_result, markdown) where:
    - json_result is the parsed JSON dict if VQA returned parseable JSON, else None.
    - markdown is the raw text from VQA output (for logging/fallback), or None if
      VQA mode is not supported.
    """
    try:
        output = pipeline.predict(input=image_path, query=_EXTRACTION_QUERY)
    except TypeError:
        # predict() does not accept a 'query' keyword argument in this version.
        return None, None
    except Exception:  # noqa: BLE001
        return None, None

    # Collect text from VQA output — the answer may live in different attributes
    # depending on the PaddleOCR 3.x version.
    text = _collect_vqa_text(output)
    if not text:
        return None, None

    json_result = _try_parse_json(text)
    return json_result, text


def _collect_vqa_text(output) -> str:
    """Extract the answer text from a VQA predict() result."""
    parts: list[str] = []
    for res in output:
        # PaddleOCR 3.x VQA pipelines may put the answer in different places.
        for attr in ("result", "answer", "text", "markdown", "rec_markdown"):
            val = getattr(res, attr, None)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
                break
        else:
            # dict-like access
            for key in ("result", "answer", "text", "markdown", "rec_markdown"):
                try:
                    val = res[key]
                    if isinstance(val, str) and val.strip():
                        parts.append(val.strip())
                        break
                except (KeyError, TypeError):
                    pass

    return "\n\n".join(parts)


def _try_parse_json(text: str) -> dict | None:
    """Strip markdown fences and try to parse text as JSON dict."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]
    except (json.JSONDecodeError, ValueError):
        pass
    return None


# ── Markdown extraction from PaddleOCR-VL result ─────────────────────────────

def _collect_markdown(output) -> str:
    parts: list[str] = []

    for res in output:
        text = _try_direct(res)
        if text:
            parts.append(text)
            continue

        # save_to_markdown() writes files; read them back
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                res.save_to_markdown(save_path=tmpdir)
                for fname in sorted(os.listdir(tmpdir)):
                    if fname.endswith(".md"):
                        with open(os.path.join(tmpdir, fname), encoding="utf-8") as f:
                            parts.append(f.read())
        except Exception:  # noqa: BLE001
            fallback = str(res)
            if fallback.strip():
                parts.append(fallback)

    return "\n\n".join(parts)


def _try_direct(res) -> str:
    for attr in ("markdown", "rec_markdown", "text", "result", "answer"):
        val = getattr(res, attr, None)
        if isinstance(val, str) and val.strip():
            return val
    try:
        for key in ("markdown", "rec_markdown", "text", "result", "answer"):
            val = res[key]
            if isinstance(val, str) and val.strip():
                return val
    except (KeyError, TypeError):
        pass
    return ""


# ── Memory cleanup ───────────────────────────────────────────────────────────

def _free_memory(device: str) -> None:
    """
    Explicitly release GPU and CPU memory before the worker process exits.

    Even though the subprocess is discarded after each extraction, calling this
    ensures CUDA tensors are freed and the CUDA context is flushed *before* the
    process returns — so the next extraction starts with a clean slate rather
    than waiting for the OS to reclaim memory asynchronously.
    """
    import gc

    # 1. Drop cached GPU tensor pool (equivalent to torch.cuda.empty_cache)
    if "gpu" in device.lower():
        try:
            import paddle  # type: ignore[import]
            paddle.device.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    # 2. Force Python GC to collect circular references and free CPU memory
    gc.collect()


# ── JSON output helpers ───────────────────────────────────────────────────────

def _ok(markdown: str, json_result: dict | None = None) -> None:
    print(json.dumps({"ok": True, "markdown": markdown, "json_result": json_result}), flush=True)


def _fail(msg: str) -> None:
    print(json.dumps({"ok": False, "error": msg}), flush=True)


if __name__ == "__main__":
    sys.exit(main())
