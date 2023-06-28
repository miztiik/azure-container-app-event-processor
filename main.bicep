// targetScope = 'subscription'

targetScope = 'resourceGroup'

// Parameters
param deploymentParams object
param identityParams object

param storageAccountParams object

param logAnalyticsWorkspaceParams object
param dceParams object
param brandTags object

param vnetParams object
param svc_bus_params object

param funcParams object
param acr_params object
param container_app_params object
param cosmosDbParams object

param dateNow string = utcNow('yyyy-MM-dd-hh-mm')

param tags object = union(brandTags, { last_deployed: dateNow })

@description('Create Identity')
module r_uami 'modules/identity/create_uami.bicep' = {
  name: '${deploymentParams.enterprise_name_suffix}_${deploymentParams.loc_short_code}_${deploymentParams.global_uniqueness}_uami'
  params: {
    deploymentParams: deploymentParams
    identityParams: identityParams
    tags: tags
  }
}

@description('Create Cosmos DB')
module r_cosmosdb 'modules/database/cosmos.bicep' = {
  name: '${cosmosDbParams.cosmosDbNamePrefix}_${deploymentParams.loc_short_code}_${deploymentParams.global_uniqueness}_cosmos_db'
  params: {
    deploymentParams: deploymentParams
    cosmosDbParams: cosmosDbParams
    tags: tags
  }
}

@description('Create the Log Analytics Workspace')
module r_logAnalyticsWorkspace 'modules/monitor/log_analytics_workspace.bicep' = {
  name: '${logAnalyticsWorkspaceParams.workspaceName}_${deploymentParams.loc_short_code}_${deploymentParams.global_uniqueness}_la'
  params: {
    deploymentParams: deploymentParams
    logAnalyticsWorkspaceParams: logAnalyticsWorkspaceParams
    tags: tags
  }
}

@description('Create Storage Account')
module r_sa 'modules/storage/create_storage_account.bicep' = {
  name: '${storageAccountParams.storageAccountNamePrefix}_${deploymentParams.loc_short_code}_${deploymentParams.global_uniqueness}_sa'
  params: {
    deploymentParams: deploymentParams
    storageAccountParams: storageAccountParams
    funcParams: funcParams
    tags: tags
  }
}

@description('Create Storage Account - Blob container')
module r_blob 'modules/storage/create_blob.bicep' = {
  name: '${storageAccountParams.storageAccountNamePrefix}_${deploymentParams.loc_short_code}_${deploymentParams.global_uniqueness}_blob'
  params: {
    deploymentParams: deploymentParams
    storageAccountParams: storageAccountParams
    storageAccountName: r_sa.outputs.saName
    storageAccountName_1: r_sa.outputs.saName_1
    logAnalyticsWorkspaceId: r_logAnalyticsWorkspace.outputs.logAnalyticsPayGWorkspaceId
    enableDiagnostics: false
  }
  dependsOn: [
    r_sa
    r_logAnalyticsWorkspace
  ]
}

@description('Create the Service Bus & Queue')
module r_svc_bus 'modules/integration/create_svc_bus.bicep' = {
  // scope: resourceGroup(r_rg.name)
  name: '${svc_bus_params.name_prefix}_${deploymentParams.global_uniqueness}_Svc_Bus'
  params: {
    deploymentParams: deploymentParams
    svc_bus_params: svc_bus_params
    tags: tags
  }
}

// Create Data Collection Endpoint
module r_dataCollectionEndpoint 'modules/monitor/data_collection_endpoint.bicep' = {
  name: '${dceParams.endpointNamePrefix}_${deploymentParams.global_uniqueness}_Dce'
  params: {
    deploymentParams: deploymentParams
    dceParams: dceParams
    osKind: 'linux'
    tags: tags
  }
}

// Create the Data Collection Rule
module r_dataCollectionRule 'modules/monitor/data_collection_rule.bicep' = {
  name: '${logAnalyticsWorkspaceParams.workspaceName}_${deploymentParams.global_uniqueness}_Dcr'
  params: {
    deploymentParams: deploymentParams
    osKind: 'Linux'
    tags: tags

    storeEventsRuleName: 'storeEvents_Dcr'
    storeEventsLogFilePattern: '/var/log/miztiik*.json'
    storeEventscustomTableNamePrefix: r_logAnalyticsWorkspace.outputs.storeEventsCustomTableNamePrefix

    automationEventsRuleName: 'miztiikAutomation_Dcr'
    automationEventsLogFilePattern: '/var/log/miztiik-automation-*.log'
    automationEventsCustomTableNamePrefix: r_logAnalyticsWorkspace.outputs.automationEventsCustomTableNamePrefix

    managedRunCmdRuleName: 'miztiikManagedRunCmd_Dcr'
    managedRunCmdLogFilePattern: '/var/log/azure/run-command-handler/*.log'
    managedRunCmdCustomTableNamePrefix: r_logAnalyticsWorkspace.outputs.managedRunCmdCustomTableNamePrefix

    linDataCollectionEndpointId: r_dataCollectionEndpoint.outputs.linDataCollectionEndpointId
    logAnalyticsPayGWorkspaceName: r_logAnalyticsWorkspace.outputs.logAnalyticsPayGWorkspaceName
    logAnalyticsPayGWorkspaceId: r_logAnalyticsWorkspace.outputs.logAnalyticsPayGWorkspaceId

  }
  dependsOn: [
    r_logAnalyticsWorkspace
  ]
}

// Create the VNets
module r_vnet 'modules/vnet/create_vnet.bicep' = {
  name: '${vnetParams.vnetNamePrefix}_${deploymentParams.global_uniqueness}_Vnet'
  params: {
    deploymentParams: deploymentParams
    vnetParams: vnetParams
    tags: tags
  }
}

@description('Add Permissions to UAMI')
module r_add_perms_to_uami 'modules/identity/assign_perms_to_uami.bicep' = {
  name: 'perms_provider_to_uami_${deploymentParams.global_uniqueness}'
  params: {
    uami_name_akane: r_uami.outputs.uami_name_akane
  }
  dependsOn: [
    r_uami
  ]
}

@description('Create Container Registry')
module r_container_registry 'modules/containers/create_container_registry.bicep' = {
  name: '${container_app_params.name_prefix}_${deploymentParams.loc_short_code}_${deploymentParams.global_uniqueness}_container_registry'
  params: {
    acr_params: acr_params
    deploymentParams: deploymentParams
    tags: tags
    uami_name_akane: r_uami.outputs.uami_name_akane
    logAnalyticsWorkspaceId: r_logAnalyticsWorkspace.outputs.logAnalyticsPayGWorkspaceId
  }
}

@description('Create Container App including managed environments')
module r_container_app 'modules/containers/create_container_apps.bicep' = {
  name: '${container_app_params.name_prefix}_${deploymentParams.loc_short_code}_${deploymentParams.global_uniqueness}_container_app'
  params: {
    container_app_params: container_app_params
    deploymentParams: deploymentParams
    tags: tags
    uami_name_akane: r_uami.outputs.uami_name_akane
    logAnalyticsWorkspaceName: r_logAnalyticsWorkspace.outputs.logAnalyticsPayGWorkspaceName
    acr_name: r_container_registry.outputs.acr_name

    saName: r_sa.outputs.saName
    blobContainerName: r_blob.outputs.blobContainerName

    cosmos_db_accnt_name: r_cosmosdb.outputs.cosmos_db_accnt_name
    cosmos_db_name: r_cosmosdb.outputs.cosmos_db_name
    cosmos_db_container_name: r_cosmosdb.outputs.cosmos_db_container_name

    svc_bus_ns_name: r_svc_bus.outputs.svc_bus_ns_name
    svc_bus_q_name: r_svc_bus.outputs.svc_bus_q_name

  }
  dependsOn: [
    r_container_registry
    r_add_perms_to_uami
  ]
}
