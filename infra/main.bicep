// ══════════════════════════════════════════════════════════════
// Azure Video Podcaster - Infrastructure as Code (Bicep)
// Deploys: Speech Service + Container Registry + Container App
// ══════════════════════════════════════════════════════════════

targetScope = 'resourceGroup'

@description('Base name for all resources')
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

// ─── Variables ──────────────────────────────────────────────

var uniqueSuffix = uniqueString(resourceGroup().id)
var speechName = '${baseName}-speech-${uniqueSuffix}'
var acrName = replace('${baseName}acr${uniqueSuffix}', '-', '')
var logAnalyticsName = '${baseName}-logs-${uniqueSuffix}'
var containerEnvName = '${baseName}-env-${uniqueSuffix}'
var containerAppName = '${baseName}-app'

// ─── Speech Service (S0 required for Avatar) ────────────────

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

// ─── Container Registry ─────────────────────────────────────

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// ─── Log Analytics Workspace ────────────────────────────────

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

// ─── Container Apps Environment ─────────────────────────────

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ─── Container App ──────────────────────────────────────────

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
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
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'speech-key'
          value: speechService.listKeys().key1
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
              name: 'AZURE_SPEECH_KEY'
              secretRef: 'speech-key'
            }
            {
              name: 'AZURE_SPEECH_REGION'
              value: location
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

// ─── Outputs ────────────────────────────────────────────────

output speechServiceName string = speechService.name
output speechRegion string = location
output acrLoginServer string = acr.properties.loginServer
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output containerAppName string = containerApp.name
