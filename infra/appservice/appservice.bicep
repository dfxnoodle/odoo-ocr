// Azure App Service deployment for EIR OCR Platform
// Compatible with the same container image used for Container Apps.
// Deploy: az deployment group create --resource-group <rg> --template-file infra/appservice/appservice.bicep

@description('Azure region for resources')
param location string = resourceGroup().location

@description('Name prefix for all resources')
param appName string = 'eir-ocr'

@description('Container image including tag')
param containerImage string = 'eiroacr.azurecr.io/eir-ocr-platform:latest'

@description('ACR login server')
param acrLoginServer string

@description('ACR admin username')
@secure()
param acrUsername string

@description('ACR admin password')
@secure()
param acrPassword string

@description('Odoo instance URL')
param odooUrl string

@description('Odoo database name')
param odooDb string

@description('Odoo API username')
param odooUsername string

@description('Odoo API password/key')
@secure()
param odooPassword string

@description('Vertex AI GCP project ID')
param vertexProjectId string

var planName = '${appName}-plan'
var webAppName = '${appName}-app'

resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: planName
  location: location
  kind: 'linux'
  sku: {
    name: 'B2'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

resource webApp 'Microsoft.Web/sites@2023-01-01' = {
  name: webAppName
  location: location
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'DOCKER|${containerImage}'
      acrUseManagedIdentityCreds: false
      appSettings: [
        { name: 'DOCKER_REGISTRY_SERVER_URL', value: 'https://${acrLoginServer}' }
        { name: 'DOCKER_REGISTRY_SERVER_USERNAME', value: acrUsername }
        { name: 'DOCKER_REGISTRY_SERVER_PASSWORD', value: acrPassword }
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'EXTRACTION_PROVIDER', value: 'vertex' }
        { name: 'LOG_LEVEL', value: 'INFO' }
        { name: 'VERTEX_PROJECT_ID', value: vertexProjectId }
        { name: 'VERTEX_LOCATION', value: 'us-central1' }
        { name: 'VERTEX_MODEL', value: 'gemini-2.0-flash-001' }
        { name: 'ODOO_URL', value: odooUrl }
        { name: 'ODOO_DB', value: odooDb }
        { name: 'ODOO_USERNAME', value: odooUsername }
        { name: 'ODOO_PASSWORD', value: odooPassword }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'false' }
      ]
      healthCheckPath: '/api/v1/health'
    }
    httpsOnly: true
  }
}

output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output webAppName string = webApp.name
