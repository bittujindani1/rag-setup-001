import sys
from pathlib import Path
import boto3
import logging
import os
import json
import urllib
from azure.storage.blob import BlobServiceClient
from fastapi import HTTPException, UploadFile
import httpx
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from env_bootstrap import bootstrap_env
from aws.document_extractor import AWSDocumentExtractor
from provider_factory import get_config

bootstrap_env(Path(__file__).resolve().with_name(".env"))



import os
UPLOAD_BLOB_URL = os.getenv("UPLOAD_BLOB_URL")
PRESIGNED_BLOB_URL = os.getenv("PRESIGNED_BLOB_URL")
LOGGER = logging.getLogger(__name__)
DOCUMENT_EXTRACTOR = None


def get_document_extractor():
    global DOCUMENT_EXTRACTOR
    if DOCUMENT_EXTRACTOR is None:
        DOCUMENT_EXTRACTOR = AWSDocumentExtractor()
    return DOCUMENT_EXTRACTOR

# def sort_extracted_data(data):
#     """
#     Sorts the extracted JSON data:
#     - Sorts pages numerically.
#     - Sorts 'bboxes_info' within each page by 'position'.
#     """
#     # Initialize a list to hold page items
#     page_items = []

#     # Iterate over the items in the data
#     for page_num, page_content in data.items():
#         if page_num.isdigit():
#             # Convert page_num to integer
#             page_num_int = int(page_num)
#             # Append to the list as a tuple (page number as int, page content)
#             page_items.append((page_num_int, page_content))
#         else:
#             # Handle non-numeric keys if necessary
#             # For now, we will skip them
#             pass

#     # Sort the pages by page number
#     sorted_page_items = sorted(page_items, key=lambda x: x[0])

#     # Create a new dictionary to hold the sorted data
#     sorted_data = {}

#     for page_num, page_content in sorted_page_items:
#         # Sort 'bboxes_info' list within each page by 'position'
#         if 'bboxes_info' in page_content:
#             page_content['bboxes_info'] = sorted(
#                 page_content['bboxes_info'],
#                 key=lambda x: x['position']
#             )
#         # Add the sorted page content to the new dictionary
#         sorted_data[str(page_num)] = page_content  # Convert page number back to string

#     # Optionally, include other non-numeric keys in the sorted data
#     for key, value in data.items():
#         if not key.isdigit():
#             sorted_data[key] = value

#     return sorted_data

# def upload_pdf_and_download_json(pdf_path, unique_id, TEMP_DIR):
#     start_time = time.time()
    
#     # Define payload parameters consistent with the working curl command
#     payload = {
#         'html_url': '',
#         'summarize_figures_gemini': 'false',
#         'summarize_tables': 'false',
#         'extract_tables_with_gemini': 'true'
#     }

#     # Define headers, including the 'Accept' header
#     headers = {
#         'Accept': 'application/json'
#     }

#     # Prepare the file for upload
#     with open(pdf_path, 'rb') as f:
#         files = {
#             'file': (os.path.basename(pdf_path), f, 'application/pdf')
#         }

#         try:
#             # Send the POST request with both connect and read timeouts
#             response = requests.post(
#                 DOCUMENT_EXTRACTOR_API_URL,
#                 data=payload,
#                 files=files,
#                 headers=headers,
#                 timeout=(3000, 3000)  # (connect_timeout, read_timeout) in seconds
#             )

#             # Raise an exception for HTTP error responses (4xx and 5xx)
#             response.raise_for_status()

#         except requests.exceptions.Timeout:
#             raise Exception("Failed to extract data: The request timed out.")
#         except requests.exceptions.HTTPError as http_err:
#             raise Exception(f"Failed to extract data: HTTP error occurred: {http_err}")
#         except requests.exceptions.RequestException as req_err:
#             raise Exception(f"Failed to extract data: Request exception occurred: {req_err}")

#     try:
#         # Attempt to parse the JSON response
#         data = response.json()
#     except json.JSONDecodeError:
#         raise Exception("Failed to extract data: Unable to decode JSON response.")

#     # **Sorting the JSON data using the modularized function**
#     sorted_data = sort_extracted_data(data)

#     end_time = time.time()
#     elapsed_time = end_time - start_time

#     # Define the path to save the JSON data
#     json_filename = f"{unique_id}_extracted_data.json"
#     json_path = os.path.join(TEMP_DIR, json_filename)

#     # Ensure the TEMP_DIR exists
#     os.makedirs(TEMP_DIR, exist_ok=True)

#     # Save the sorted JSON data to a file
#     try:
#         with open(json_path, 'w') as json_file:
#             json.dump(sorted_data, json_file, indent=4)
#     except IOError as io_err:
#         raise Exception(f"Failed to save extracted data: {io_err}")

#     return json_path




# Download blob from Azure Blob Storage
def download_blob(connection_string, container_name, blob_url, output_file_path):
    config = get_config()
    if config.get("vector_store") == "s3" and "amazonaws.com" in blob_url:
        try:
            s3 = boto3.client("s3", region_name=config["aws_region"])
            parsed_url = urllib.parse.urlparse(blob_url)
            bucket_name = parsed_url.netloc.split(".")[0]
            key = parsed_url.path.lstrip("/")
            s3.download_file(bucket_name, key, output_file_path)
            return
        except Exception as e:
            print(f"Failed to download from S3 URL {blob_url}. Error: {e}")

    try:
        parsed_url = urllib.parse.urlparse(blob_url)
        path_parts = parsed_url.path.lstrip('/').split('/', 1)
        if len(path_parts) < 2:
            print(f"Invalid blob URL: {blob_url}")
            return
        blob_name = path_parts[1]
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        downloaded_blob = blob_client.download_blob().readall()
        with open(output_file_path, 'wb') as file:
            file.write(downloaded_blob)
        print(f"Blob downloaded successfully to {output_file_path}")
    except Exception as e:
        print(f"Failed to download blob from {blob_url}. Error: {e}")

 

from PyPDF2 import PdfReader, PdfWriter

from PyPDF2 import PdfReader, PdfWriter


def sort_extracted_data(data):
    """
    Sorts the extracted JSON data:
    - Sorts pages numerically.
    - Sorts 'bboxes_info' within each page by 'position'.
    """
    # Initialize a list to hold page items
    page_items = []

    # Iterate over the items in the data
    for page_num, page_content in data.items():
        if page_num.isdigit():
            # Convert page_num to integer
            page_num_int = int(page_num)
            # Append to the list as a tuple (page number as int, page content)
            page_items.append((page_num_int, page_content))
        else:
            # Handle non-numeric keys if necessary
            # For now, we will skip them
            pass

    # Sort the pages by page number
    sorted_page_items = sorted(page_items, key=lambda x: x[0])

    # Create a new dictionary to hold the sorted data
    sorted_data = {}

    for page_num, page_content in sorted_page_items:
        # Sort 'bboxes_info' list within each page by 'position'
        if 'bboxes_info' in page_content:
            page_content['bboxes_info'] = sorted(
                page_content['bboxes_info'],
                key=lambda x: x['position']
            )
        # Add the sorted page content to the new dictionary
        sorted_data[str(page_num)] = page_content  # Convert page number back to string

    # Optionally, include other non-numeric keys in the sorted data
    for key, value in data.items():
        if not key.isdigit():
            sorted_data[key] = value

    return sorted_data

def split_pdf(pdf_path, pages_per_file, output_dir):
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    output_files = []

    for start_page in range(0, total_pages, pages_per_file):
        writer = PdfWriter()
        end_page = min(start_page + pages_per_file, total_pages)
        for page in range(start_page, end_page):
            writer.add_page(reader.pages[page])
        output_filename = f"{os.path.splitext(os.path.basename(pdf_path))[0]}_{start_page//pages_per_file + 1}.pdf"
        output_filepath = os.path.join(output_dir, output_filename)
        with open(output_filepath, 'wb') as f:
            writer.write(f)
        output_files.append(output_filepath)

    return output_files

def _structured_pages_to_legacy_json(pages, file_name, input_file_url):
    payload = {}
    for page in pages:
        page_number = str(page.get("page_number"))
        text = page.get("text", "")
        images = page.get("images", [])
        tables = page.get("tables", [])
        page_image_url = page.get("page_image_url", "")

        bboxes_info = []
        if text:
            bboxes_info.append(
                {
                    "label": "TEXT",
                    "output": text,
                    "page_num": int(page_number),
                }
            )

        for image_url in images:
            bboxes_info.append(
                {
                    "label": "FIGURE",
                    "output": None,
                    "page_num": int(page_number),
                    "img_url": image_url,
                }
            )

        for table in tables:
            bboxes_info.append(
                {
                    "label": "TABLE",
                    "output": table.get("text", ""),
                    "page_num": int(page_number),
                    "img_url": table.get("image_url", ""),
                }
            )

        payload[page_number] = {
            "bbox_img_url": page_image_url,
            "bboxes_info": bboxes_info,
        }

    payload["bbox_pdf_url"] = "none"
    payload["file_name"] = file_name
    payload["input_file_url"] = input_file_url
    return payload

def merge_jsons(json_data_list, file_name, input_file_url):
    merged_data = {}
    page_offset = 0
    for data in json_data_list:
        for key, value in data.items():
            if key.isdigit():  # Only renumber pages
                new_key = str(int(key) + page_offset)
                merged_data[new_key] = value
            else:
                merged_data[key] = value
        page_offset += len([k for k in data.keys() if k.isdigit()])
    
    # Append specific keys at the end
    merged_data['bbox_pdf_url'] = 'none'
    merged_data['file_name'] = file_name
    merged_data['input_file_url'] = input_file_url
    
    return merged_data

def upload_pdf_and_download_json(pdf_path, pages_per_file, temp_dir, filename, input_file_url):
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    print("document extractor function aws-native-extractor")
    pages = get_document_extractor().extract_document(pdf_path, filename)
    final_data = _structured_pages_to_legacy_json(pages, filename, input_file_url)
    print("final_data", final_data)
    # Save the final merged JSON data
    final_json_path = os.path.join(temp_dir, 'final_extracted_data.json')
    with open(final_json_path, 'w') as json_file:
        json.dump(final_data, json_file, indent=4)

    return final_json_path





def upload_to_blob(
    file: UploadFile,
    storage_account_name: str,
    container_name: str,
    local_file_path: str | None = None,
):
    config = get_config()
    if config.get("vector_store") == "s3":
        s3 = boto3.client("s3", region_name=config["aws_region"])
        if local_file_path:
            with open(local_file_path, "rb") as handle:
                s3.upload_fileobj(handle, config["s3_bucket_documents"], f"{container_name}/{file.filename}")
        else:
            file.file.seek(0)
            s3.upload_fileobj(file.file, config["s3_bucket_documents"], f"{container_name}/{file.filename}")
        return True

    with httpx.Client() as client:
        

        file_content = file.file.read()  # Read file content synchronously
        files = {
            'files': (file.filename, file_content, file.content_type)
        }
        data = {
            'storage_account_name': storage_account_name,
            'container_name': container_name,
        }
        try:
            print("Uploading data",data)
            print(UPLOAD_BLOB_URL)
            response = client.post(UPLOAD_BLOB_URL, headers={"accept": "application/json"}, data=data, files=files)
            # Check for a range of success codes
            if response.status_code not in [200, 201, 202]:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error uploading file: {response.json().get('message', 'Unknown error')}"
                )

            # return {"status": "Success", "message": "File uploaded successfully"}

            return True
        except httpx.HTTPError as e:

            raise HTTPException(status_code=500, detail="HTTP error during file upload")
        except Exception as e:

            raise HTTPException(status_code=500, detail="Unexpected error during file upload")



def get_presigned_url(blob_name: str, storage_account_name: str, container_name: str):
    config = get_config()
    if config.get("vector_store") == "s3":
        s3 = boto3.client("s3", region_name=config["aws_region"])
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": config["s3_bucket_documents"], "Key": f"{container_name}/{blob_name}"},
            ExpiresIn=3600,
        )

    with httpx.Client() as client:
        

        data = {
            'storage_account_name': storage_account_name,
            'container_name': container_name,
            'blob_name': blob_name
        }

        try:
            response = client.post(PRESIGNED_BLOB_URL, headers={"accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}, data=data)

            if response.status_code != 200:

                raise HTTPException(status_code=response.status_code, detail="Error generating presigned URL")

            presigned_url = response.json().get("blob_url")
            
            return presigned_url

        except httpx.HTTPError as e:
            
            raise HTTPException(status_code=500, detail="Error generating presigned URL")
