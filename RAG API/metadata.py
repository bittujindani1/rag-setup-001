

def create_image_metadata(imageresult, file_name, input_file_url):
    image_metadata = []

    # Sort the keys to ensure consistent ordering
    sorted_keys = sorted(imageresult.keys(), key=lambda x: int(x))

    for idx, key in enumerate(sorted_keys):
        entry = imageresult[key]

        # Handle page_numbers: convert list to comma-separated string if multiple
        page_numbers = entry.get("page_numbers", [])
        if not page_numbers:
            page_numbers_str = "N/A"
        elif len(page_numbers) == 1:
            page_numbers_str = str(page_numbers[0])
        else:
            page_numbers_str = ",".join(map(str, page_numbers))

        # Construct metadata dictionary
        metadata_entry = {
            "type": entry.get("type", "FIGURE"),
            "url": entry.get("url", ""),
            "page_numbers": page_numbers_str,
            "filename": file_name,
            "pdf_url": input_file_url
        }

        image_metadata.append(metadata_entry)

    return image_metadata


# Function to create table_metadata list
def create_table_metadata(tableresult, file_name, input_file_url):

    table_metadata = []

    # Sort the keys to ensure consistent ordering
    sorted_keys = sorted(tableresult.keys(), key=lambda x: int(x))

    for idx, key in enumerate(sorted_keys):
        entry = tableresult[key]

        # Handle page_numbers: convert list to comma-separated string if multiple
        page_numbers = entry.get("page_numbers", [])
        if not page_numbers:
            page_numbers_str = "N/A"
        elif len(page_numbers) == 1:
            page_numbers_str = str(page_numbers[0])
        else:
            page_numbers_str = ",".join(map(str, page_numbers))

        # Construct metadata dictionary
        metadata_entry = {
            "type": entry.get("type", "TABLE"),
            "url": entry.get("url", ""),
            "page_numbers": page_numbers_str,
            "filename": file_name,
            "pdf_url": input_file_url
        }

        table_metadata.append(metadata_entry)

    return table_metadata

 
# Function to create text_metadata list
def create_text_metadata(textresult, file_name, input_file_url):
    text_metadata = []

    # Sort the keys to ensure consistent ordering
    sorted_keys = sorted(textresult.keys(), key=lambda x: int(x))

    for key in sorted_keys:
        entry = textresult[key]

        # Handle page_numbers: convert list to comma-separated string if multiple
        page_numbers = entry.get("page_numbers", [])
        if not page_numbers:
            page_numbers_str = "N/A"
        elif len(page_numbers) == 1:
            page_numbers_str = str(page_numbers[0])
        else:
            page_numbers_str = ",".join(map(str, page_numbers))

        # Handle url: convert list to comma-separated string if multiple
        urls = entry.get("url", [])
        if not urls:
            url_str = "N/A"
        elif len(urls) == 1:
            url_str = urls[0]
        else:
            url_str = ",".join(urls)

        # Construct metadata dictionary
        metadata_entry = {
            "type": entry.get("type", "TEXT"),
            "url": url_str,
            "page_numbers": page_numbers_str,
            "filename": file_name,
            "pdf_url": input_file_url
        }

        text_metadata.append(metadata_entry)

    return text_metadata




# Preprocess metadata synchronously
def preprocess_metadata(chunks):
    preprocessed_data = []
    for chunk in chunks:
        metadata = chunk.metadata.copy()
        if 'doc_id' in metadata:
            del metadata['doc_id']
        if 'url' in metadata and isinstance(metadata['url'], str):
            metadata['url'] = metadata['url'].split(',')
        if 'page_numbers' in metadata and isinstance(metadata['page_numbers'], str):
            metadata['page_numbers'] = metadata['page_numbers'].split(',')
        preprocessed_data.append(metadata)
    return preprocessed_data