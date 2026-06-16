// Resource-group-scoped workload for the RAG cost-optimization demo.
// All data-plane auth is Entra-only (no API keys) so the template works in
// tenants where Azure Policy forces `disableLocalAuth=true`.

@description('Azure region for AI Foundry + model deployments.')
param location string

@description('Azure region for the AI Search service. Override if `location` is capacity-constrained for Search.')
param searchLocation string = location

@description('Short lowercase prefix.')
param namePrefix string

@description('Tags applied to every resource.')
param tags object

@description('Object ID of the principal that will run the demo. Empty -> skip RBAC.')
param principalId string = ''

@allowed([
  'User'
  'ServicePrincipal'
])
param principalType string = 'User'

// ---- Names -------------------------------------------------------------------
var suffix = toLower(uniqueString(resourceGroup().id))
var aifName = '${namePrefix}-aif-${suffix}'
var searchName = '${namePrefix}-search-${suffix}'
var projectName = 'rag-cost-project'
var embeddingDeploymentName = 'text-embedding-3-small'
var chatDeploymentName = 'gpt-4o-mini'
var searchIndexName = 'rag-cost-demo'

// ---- Built-in role IDs -------------------------------------------------------
var roleCognitiveServicesOpenAIUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var roleCognitiveServicesUser       = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var roleAzureAIDeveloper            = '64702f94-c441-49e6-a78b-ef80e0188fee'
var roleSearchServiceContributor    = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
var roleSearchIndexDataContributor  = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var roleSearchIndexDataReader       = '1407120a-92aa-4202-b7e9-c0e197c71c8f'

// ---- Azure AI Foundry account (Cognitive Services AIServices) ----------------
// `allowProjectManagement: true` is required to create Foundry projects under
// this account. `disableLocalAuth: true` aligns with the common enterprise
// policy and forces Entra auth on the data plane.
resource aif 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: aifName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: aifName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
    #disable-next-line BCP037
    allowProjectManagement: true
  }
}

// Serialize the two deployments so we don't race on the same account.
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aif
  name: embeddingDeploymentName
  sku: {
    name: 'Standard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
    raiPolicyName: 'Microsoft.Default'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aif
  name: chatDeploymentName
  dependsOn: [
    embeddingDeployment
  ]
  sku: {
    name: 'GlobalStandard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
    raiPolicyName: 'Microsoft.Default'
  }
}

// ---- Foundry project ---------------------------------------------------------
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aif
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: 'RAG Cost Demo'
    description: 'Foundry project for the RAG cost-optimization demo.'
  }
}

// ---- Azure AI Search ---------------------------------------------------------
// AAD-only auth so the resource is policy-compliant and we never depend on
// admin keys. `searchLocation` is separate so you can dodge eastus2 capacity.
resource search 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: searchName
  location: searchLocation
  tags: tags
  sku: {
    name: 'basic'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    semanticSearch: 'free'
    disableLocalAuth: true
  }
}

// ---- RBAC for the user/SP running the demo ----------------------------------
resource raAoaiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(aif.id, principalId, roleCognitiveServicesOpenAIUser)
  scope: aif
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleCognitiveServicesOpenAIUser)
  }
}

resource raAiDev 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(aif.id, principalId, roleAzureAIDeveloper)
  scope: aif
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAzureAIDeveloper)
  }
}

resource raAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(aif.id, principalId, roleCognitiveServicesUser)
  scope: aif
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleCognitiveServicesUser)
  }
}

resource raSearchService 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, roleSearchServiceContributor)
  scope: search
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchServiceContributor)
  }
}

resource raSearchIndex 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, roleSearchIndexDataContributor)
  scope: search
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchIndexDataContributor)
  }
}

// Foundry project's managed identity needs to read the search index when the
// agent's azure_ai_search tool is invoked via the AAD connection. The Foundry
// runtime also calls control-plane Search APIs (list indexes), which requires
// Search Service Contributor in addition to Search Index Data Reader.
resource raProjectSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, foundryProject.id, roleSearchIndexDataReader)
  scope: search
  properties: {
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchIndexDataReader)
  }
}

resource raProjectSearchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, foundryProject.id, roleSearchServiceContributor)
  scope: search
  properties: {
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchServiceContributor)
  }
}

// ---- Outputs ----------------------------------------------------------------
// Use the canonical openai.azure.com endpoint so the existing client code
// continues to work unchanged. AIServices accounts serve both endpoints.
// No keys are emitted: all clients authenticate via DefaultAzureCredential.
output aoaiEndpoint string = 'https://${aif.name}.openai.azure.com/'
output embeddingDeployment string = embeddingDeployment.name
output chatDeployment string = chatDeployment.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchIndex string = searchIndexName
output foundryProjectEndpoint string = 'https://${aif.name}.services.ai.azure.com/api/projects/${foundryProject.name}'
