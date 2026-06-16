// Subscription-scope entry point. Creates a dedicated resource group for the
// RAG cost-optimization demo and then materializes the workload inside it.

targetScope = 'subscription'

@minLength(1)
@maxLength(20)
@description('Logical environment name (e.g. dev, demo). Used to suffix the resource group.')
param environmentName string

@minLength(2)
@description('Azure region for AI Foundry + model deployments.')
param location string

@description('Azure region for AI Search. Defaults to `location`; override (e.g. `eastus`, `westus3`) if the primary region is capacity-constrained.')
param searchLocation string = ''

@minLength(3)
@maxLength(10)
@description('Short lowercase prefix for resource names.')
param namePrefix string = 'ragcost'

@description('Object ID of the principal that will run the demo locally. Receives data-plane RBAC. Leave empty to skip role assignments.')
param principalId string = ''

@allowed([
  'User'
  'ServicePrincipal'
])
@description('Type of the principal receiving role assignments.')
param principalType string = 'User'

var resourceGroupName = 'rg-${namePrefix}-${environmentName}'
var tags = {
  'azd-env-name': environmentName
  project: 'rag-cost-optimized'
  purpose: 'demo'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module workload 'resources.bicep' = {
  name: 'workload'
  scope: rg
  params: {
    location: location
    searchLocation: empty(searchLocation) ? location : searchLocation
    namePrefix: namePrefix
    tags: tags
    principalId: principalId
    principalType: principalType
  }
}

// ---- Outputs (consumed by the postprovision hook to populate backend/.env) ----
// No API keys: data-plane auth is AAD via DefaultAzureCredential.
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_OPENAI_ENDPOINT string = workload.outputs.aoaiEndpoint
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = workload.outputs.embeddingDeployment
output AZURE_OPENAI_CHAT_DEPLOYMENT string = workload.outputs.chatDeployment
output AZURE_AI_SEARCH_ENDPOINT string = workload.outputs.searchEndpoint
output AZURE_AI_SEARCH_INDEX string = workload.outputs.searchIndex
output FOUNDRY_PROJECT_ENDPOINT string = workload.outputs.foundryProjectEndpoint
