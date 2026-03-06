#!/bin/bash
# ══════════════════════════════════════════════════════════════
# Azure Video Podcaster - Deployment Script
# ══════════════════════════════════════════════════════════════
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-video-podcaster}"
LOCATION="${LOCATION:-westeurope}"
BASE_NAME="${BASE_NAME:-videopodcaster}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "╔══════════════════════════════════════════════════════╗"
echo "║     Azure Video Podcaster - Deployment              ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Resource Group: $RESOURCE_GROUP"
echo "║  Location:       $LOCATION"
echo "║  Base Name:      $BASE_NAME"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ─── Step 1: Login check ────────────────────────────────────
echo "🔐 Checking Azure CLI login..."
az account show > /dev/null 2>&1 || {
    echo "  → Please login first: az login"
    exit 1
}
echo "  ✅ Logged in as: $(az account show --query user.name -o tsv)"
echo ""

# ─── Step 2: Create Resource Group ──────────────────────────
echo "📦 Creating Resource Group..."
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none
echo "  ✅ Resource Group ready"
echo ""

# ─── Step 3: Deploy Infrastructure (Bicep) ──────────────────
echo "🏗️  Deploying infrastructure (Bicep)..."
DEPLOY_OUTPUT=$(az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file infra/main.bicep \
    --parameters baseName="$BASE_NAME" location="$LOCATION" imageTag="$IMAGE_TAG" \
    --query "properties.outputs" \
    --output json)

ACR_LOGIN_SERVER=$(echo "$DEPLOY_OUTPUT" | jq -r '.acrLoginServer.value')
CONTAINER_APP_NAME=$(echo "$DEPLOY_OUTPUT" | jq -r '.containerAppName.value')
APP_URL=$(echo "$DEPLOY_OUTPUT" | jq -r '.containerAppUrl.value')

echo "  ✅ Infrastructure deployed"
echo "  → ACR: $ACR_LOGIN_SERVER"
echo "  → App URL: $APP_URL"
echo ""

# ─── Step 4: Build and Push Docker Image ────────────────────
echo "🐳 Building and pushing Docker image..."
az acr login --name "${ACR_LOGIN_SERVER%%.*}"
az acr build \
    --registry "${ACR_LOGIN_SERVER%%.*}" \
    --image "${BASE_NAME}:${IMAGE_TAG}" \
    --file Dockerfile \
    .
echo "  ✅ Image pushed to ACR"
echo ""

# ─── Step 5: Update Container App ───────────────────────────
echo "🔄 Updating Container App with new image..."
az containerapp update \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "${ACR_LOGIN_SERVER}/${BASE_NAME}:${IMAGE_TAG}" \
    --output none
echo "  ✅ Container App updated"
echo ""

# ─── Done ────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅  DEPLOYMENT COMPLETE                            ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  App URL:  $APP_URL"
echo "║  API Docs: ${APP_URL}/docs"
echo "║  Health:   ${APP_URL}/health"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "📝 Quick test:"
echo "  curl -X POST ${APP_URL}/podcast/generate \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\": \"Benvenuti al nostro podcast...\", \"title\": \"Test Episode\"}'"
