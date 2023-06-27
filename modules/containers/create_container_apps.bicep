// SET MODULE DATE
param module_metadata object = {
  module_last_updated: '2023-06-25'
  owner: 'miztiik@github'
}

param deploymentParams object
param tags object

param uami_name_akane string
param logAnalyticsWorkspaceName string

param container_app_params object
param acr_name string

@description('Get Log Analytics Workspace Reference')
resource r_logAnalyticsPayGWorkspace_ref 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: logAnalyticsWorkspaceName
}

@description('Reference existing User-Assigned Identity')
resource r_uami_container_app 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: uami_name_akane
}

@description('Get Container Registry Reference')
resource r_acr 'Microsoft.ContainerRegistry/registries@2022-02-01-preview' existing = {
  name: acr_name
}

var _app_name = replace('${deploymentParams.enterprise_name_suffix}-${deploymentParams.loc_short_code}-${container_app_params.name_prefix}-${deploymentParams.global_uniqueness}', '_', '')

resource r_mgd_env 'Microsoft.App/managedEnvironments@2022-11-01-preview' = {
  name: '${_app_name}-mgd-env'
  location: deploymentParams.location
  tags: tags

  properties: {
    zoneRedundant: false // Available only for Premium SKU
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: r_logAnalyticsPayGWorkspace_ref.properties.customerId
        sharedKey: r_logAnalyticsPayGWorkspace_ref.listKeys().primarySharedKey
      }
    }
  }
}

resource r_container_app 'Microsoft.App/containerApps@2022-01-01-preview' = {
  name: 'con-app-${deploymentParams.loc_short_code}-${deploymentParams.global_uniqueness}'
  location: deploymentParams.location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${r_uami_container_app.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: r_mgd_env.id
    configuration: {
      secrets: [
        {
          name: 'registry-password'
          value: r_acr.listCredentials().passwords[0].value
        }
      ]
      registries: [
        {
          server: '${r_acr.name}.azurecr.io'
          username: r_acr.name
          passwordSecretRef: 'registry-password'
        }
      ]
      ingress: {
        external: true
        targetPort: 80
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
    }
    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling-rule'
            http: {
              metadata: {
                concurrentRequests: '3'
              }
            }
          }
        ]
      }
      containers: [
        {
          env: [
            {
              name: 'APPINSIGHTS_INSTRUMENTATIONKEY'
              value: r_logAnalyticsPayGWorkspace_ref.properties.customerId
            }
          ]
          // image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          name: 'miztiik-flask-app'
          // image: '${sys.toLower(acr_name)}.azurecr.io/miztiik/echo-hello:latest'
          // image: '${sys.toLower(acr_name)}.azurecr.io/miztiik/flask-web-server:latest'
          image: '${sys.toLower(acr_name)}.azurecr.io/miztiik/event-producer:latest'
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
        }
      ]
    }
  }
}

// OUTPUTS
output module_metadata object = module_metadata

output fqdn string = r_container_app.properties.configuration.ingress.fqdn
