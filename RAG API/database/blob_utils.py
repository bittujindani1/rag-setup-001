import logging
from fastapi import HTTPException, UploadFile
import httpx

from env_bootstrap import bootstrap_env

bootstrap_env()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


import os
UPLOAD_BLOB_URL = os.getenv("UPLOAD_BLOB_URL")
PRESIGNED_BLOB_URL = os.getenv("PRESIGNED_BLOB_URL")

# Utility function to handle file upload to blob storage
async def upload_to_blob(file: UploadFile, storage_account_name: str, container_name: str):
    async with httpx.AsyncClient() as client:
        logger.info(f"Preparing to upload file {file.filename} to blob storage under container: {container_name}")

        # Read the file content
        file_content = await file.read()
        files = {
            'files': (file.filename, file_content, file.content_type)
        }

        # Payload to be sent to the blob storage upload API
        data = {
            'storage_account_name': storage_account_name,
            'container_name': container_name,
        }

        try:
            response = await client.post(UPLOAD_BLOB_URL, headers={"accept": "application/json"}, data=data, files=files)
            logger.info(f"File upload status code: {response.status_code}")
            logger.debug(f"Upload response: {response.text}")

            if response.status_code != 200:
                logger.error(f"File upload failed for {file.filename}")
                raise HTTPException(status_code=response.status_code, detail="Error uploading file to blob storage")

            logger.info(f"File {file.filename} successfully uploaded to container {container_name}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Error during upload: {str(e)}")
            raise HTTPException(status_code=500, detail="Error uploading file to blob storage")


# Utility function to get presigned URL
async def get_presigned_url(blob_name: str, storage_account_name: str, container_name: str):
    async with httpx.AsyncClient() as client:
        logger.info(f"Requesting presigned URL for blob: {blob_name} in container: {container_name}")

        data = {
            'storage_account_name': storage_account_name,
            'container_name': container_name,
            'blob_name': blob_name
        }

        try:
            response = await client.post(PRESIGNED_BLOB_URL, headers={"accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}, data=data)
            logger.info(f"Presigned URL request status code: {response.status_code}")
            logger.debug(f"Presigned URL response: {response.text}")

            if response.status_code != 200:
                logger.error(f"Failed to get presigned URL for {blob_name} in container {container_name}")
                raise HTTPException(status_code=response.status_code, detail="Error generating presigned URL")

            presigned_url = response.json().get("blob_url")
            logger.info(f"Generated presigned URL: {presigned_url}")
            return presigned_url

        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting presigned URL: {str(e)}")
            raise HTTPException(status_code=500, detail="Error generating presigned URL")
