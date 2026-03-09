// ======================================================================
// Azure Video Podcaster - Infrastructure as Code (Bicep)
// Deploys: Speech Service + Storage + Container Registry + Container App
//          + Azure OpenAI (optional)
// ======================================================================

targetScope = 'resourceGroup'

@description('Base name for all resources')
@minLength(3)
param baseName string = 'videopodcaster'

@description('Azure region - MUST be a region that supports TTS Avatar')
@allowed([
  'westeurope'
  'westus2'
  'southeastasia'
])
param location string = 'westeurope'

@description('Container image tag')
param imageTag string = 'latest'

@description('Deploy Azure OpenAI Service')
param deployOpenAI bool = false

// --- Variables ---

var uniqueSuffix = uniqueString(resourceGroup().id)
var shortSuffix = substring(uniqueSuffix, 0, 8)
var speechName = '${baseName}-speech-${shortSuffix}'
var storageName = toLower(take(replace('${baseName}st${shortSuffix}', '-', ''), 24))
var acrName = toLower(take(replace('${baseName}acr${shortSuffix}', '-', ''), 50))
var logAnalyticsName = '${baseName}-logs-${shortSuffix}'
var containerEnvName = '${baseName}-cae-${shortSuffix}'
var containerAppName = '${baseName}-app'
var openaiName = '${baseName}-openai-${shortSuffix}'
var managedIdentityName = '${baseName}-id-${shortSuffix}'

// --- Managed Identity ---

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: managedIdentityName
  location: location
}

// --- Speech Service (S0 required for Avatar) ---

resource speechService 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: speechName
  location: location
  kind: 'SpeechServices'
  sku: {
    name: 'S0'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

// Cognitive Services User role for managed identity on Speech Service
resource speechRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speechService.id, managedIdentity.id, 'cognitive-services-user')
  scope: speechService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Storage Account ---

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource podcastContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'podcast-videos'
  properties: {
    publicAccess: 'None'
  }
}

// Storage Blob Data Contributor role for managed identity
resource storageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, 'storage-blob-contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Azure OpenAI (optional) ---

resource openaiService 'Microsoft.CognitiveServices/accounts@2024-10-01' = if (deployOpenAI) {
  name: openaiName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

// Cognitive Services OpenAI User role for managed identity on OpenAI Service
// This role (5e0bd9bd-7b93-4f28-af87-19fc36ad61bd) allows chat/completions calls via Entra ID token
resource openaiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployOpenAI) {
  name: guid(openaiService.id, managedIdentity.id, 'cognitive-services-openai-user')
  scope: openaiService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Container Registry ---

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

// AcrPull role for managed identity on Container Registry
resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, 'acr-pull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Log Analytics Workspace ---

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// --- Container Apps Environment ---

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'azure-monitor'
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// Diagnostic settings to send Container Apps Environment logs to Log Analytics
resource containerEnvDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'send-to-log-analytics'
  scope: containerEnv
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

// --- Container App ---

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'video-podcaster'
          image: '${acr.properties.loginServer}/${baseName}:${imageTag}'
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            {
              name: 'AZURE_SPEECH_REGION'
              value: location
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT_NAME'
              value: storageAccount.name
            }
            {
              name: 'AZURE_STORAGE_CONTAINER'
              value: 'podcast-videos'
            }
            {
              name: 'AVATAR_CHARACTER'
              value: 'lisa'
            }
            {
              name: 'AVATAR_STYLE'
              value: 'casual-sitting'
            }
            {
              name: 'TTS_VOICE'
              value: 'it-IT-DiegoNeural'
            }
            {
              name: 'TTS_LANGUAGE'
              value: 'it-IT'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentity.properties.clientId
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: deployOpenAI ? openaiService!.properties.endpoint : ''
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: 'gpt-4o'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

// --- Outputs ---

output speechServiceName string = speechService.name
output speechRegion string = location
output storageAccountName string = storageAccount.name
output acrLoginServer string = acr.properties.loginServer
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output containerAppName string = containerApp.name
output managedIdentityId string = managedIdentity.id
output openaiServiceName string = deployOpenAI ? openaiService!.name : 'not-deployed'
