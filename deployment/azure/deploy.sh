#!/bin/bash
# Azure Container Instances deployment
# Run: chmod +x deploy.sh && ./deploy.sh
# Requires: az login first

RESOURCE_GROUP="depi-healthcare-rg"
LOCATION="germanywestcentral"
ACR_NAME="depihealthcarecr"
CONTAINER_NAME="healthcare-dashboard"
IMAGE_TAG="latest"

echo "🔵 Creating resource group..."
az group create --name $RESOURCE_GROUP --location $LOCATION

echo "🔵 Creating Azure Container Registry..."
az acr create --resource-group $RESOURCE_GROUP \
              --name $ACR_NAME --sku Basic

echo "🔵 Building and pushing image..."
az acr build --registry $ACR_NAME \
             --image healthcare-dashboard:$IMAGE_TAG .

echo "🔵 Deploying to Azure Container Instances..."
az container create \
    --resource-group $RESOURCE_GROUP \
    --name $CONTAINER_NAME \
    --image "$ACR_NAME.azurecr.io/healthcare-dashboard:$IMAGE_TAG" \
    --cpu 1 --memory 1.5 \
    --registry-login-server "$ACR_NAME.azurecr.io" \
    --registry-username $(az acr credential show --name $ACR_NAME --query username -o tsv) \
    --registry-password $(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv) \
    --ports 8501 \
    --environment-variables DATABASE_URL="$DATABASE_URL" \
    --dns-name-label healthcare-depi-demo

echo "✅ Deployed! URL: http://healthcare-depi-demo.$LOCATION.azurecontainer.io:8501"