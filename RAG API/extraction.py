
# Process imageresult
def extract_imageresult(data):
    # Initialize the result dictionary
    imageresult = {}
    count = 1

    # Iterate over the pages
    for page_num_str, page_content in data.items():
        # Skip keys that are not page numbers (e.g., 'bbox_pdf_url', 'file_name')
        if not page_num_str.isdigit():
            continue
        page_num = int(page_num_str)

        # Get the list of 'bboxes_info'
        bboxes_info = page_content.get('bboxes_info', [])

        # Iterate over the bboxes_info
        for item in bboxes_info:
            # Ensure 'item' is not None and is a dictionary
            if isinstance(item, dict):
                label = item.get('label')

                # Check if 'label' exists and equals 'FIGURE' or 'TABLE'
                if label in ('FIGURE', 'TABLE'):
                    img_url = item.get('img_url')

                    # If 'img_url' is missing, skip this item
                    if not img_url:
                        continue

                    # Get 'page_num' from item or use the current page number
                    page_num_item = item.get('page_num', page_num)

                    # Set 'output' to the label type ('FIGURE' or 'TABLE')
                    output_type = label

                    # Add to result
                    imageresult[str(count)] = {
                        'output': None,
                        'type': output_type,
                        'page_numbers': [page_num_item],
                        'url': img_url
                    }
                    count += 1
    return imageresult

# Process tableresult
def extract_tableresult(data):
    # Initialize the result dictionary
    tableresult = {}
    count = 1

    # Iterate over the pages
    for page_num_str, page_content in data.items():
        # Skip keys that are not page numbers (e.g., 'bbox_pdf_url', 'file_name')
        if not page_num_str.isdigit():
            continue
        page_num = int(page_num_str)
        # Get the list of 'bboxes_info'
        bboxes_info = page_content.get('bboxes_info', [])
        # Iterate over the bboxes_info
        for item in bboxes_info:
            # Ensure 'item' is not None and is a dictionary
            if isinstance(item, dict):
                # Check if 'label' exists and equals 'TABLE'
                if item.get('label') == 'TABLE':
                    output = item.get('output')
                    # If 'output' is missing, skip this item
                    if not output:
                        continue
                    # Handle 'output' being a list or string
                    if isinstance(output, list):
                        output = '\n'.join(output)
                    elif isinstance(output, str):
                        output = output.strip()
                    else:
                        output = str(output)
                    # Get 'page_num' from item or use 'page_num'
                    page_num_item = item.get('page_num', page_num)
                    # Get 'img_url' from the TABLE item
                    img_url = item.get('img_url', '')
                    # Add to result
                    tableresult[str(count)] = {
                        'output': output,
                        'page_numbers': [page_num_item],
                        'url': img_url,
                        'type': "TABLE"
                    }
                    count += 1

    return tableresult

# Process textresult
def extract_textresult(data):
# Initialize variables
    sections = []
    current_section = None
    section_counter = 0

    # Get only the page number keys
    page_keys = [k for k in data.keys() if k.isdigit()]

    # Build a mapping from page numbers to page URLs
    page_urls = {}
    for page_num_str in sorted(page_keys, key=int):
        page_num = int(page_num_str)
        page_content = data[page_num_str]
        bbox_img_url = page_content.get('bbox_img_url')
        if bbox_img_url:
            page_urls[page_num] = bbox_img_url

    # Iterate over the pages in order
    for page_num_str in sorted(page_keys, key=int):
        page_num = int(page_num_str)
        page_content = data[page_num_str]
        bboxes_info = page_content.get('bboxes_info', [])
        for item in bboxes_info:
            # Ensure 'item' is a dictionary
            if isinstance(item, dict):
                label = item.get('label')
                output = item.get('output', '')

                # Handle 'output' being a list or string
                if isinstance(output, list):
                    output = '\n'.join(output)
                elif isinstance(output, str):
                    output = output.strip()
                else:
                    output = str(output)

                if label == 'TITLE':
                    if current_section is not None:
                        sections.append(current_section)
                    section_counter += 1
                    current_section = {
                        'output': f"title- {output}\n",
                        'page_numbers': set([page_num])
                    }
                elif label in ('TEXT', 'FORMULA', 'FIGURE', 'TABLE'):
                    if current_section is None:
                        # Initialize a default section before any TITLE
                        section_counter += 1
                        current_section = {
                            'output': '',
                            'page_numbers': set([page_num])
                        }
                    if label == 'TEXT':
                        current_section['output'] += f"{output}\n"
                    elif label == 'FORMULA':
                        current_section['output'] += f"formula- {output}\n"

                    current_section['page_numbers'].add(page_num)
                else:
                    # Skip other labels
                    continue

    # After loop ends, save the last section if it exists
    if current_section is not None:
        sections.append(current_section)

    # Build the result dictionary
    textresult = {}
    for i, section in enumerate(sections, start=1):
        page_numbers = sorted(section['page_numbers'])
        urls = [page_urls[page_num] for page_num in page_numbers if page_num in page_urls]
        textresult[str(i)] = {
            'output': section['output'],
            'page_numbers': page_numbers,
            'url': urls,
            'type': "TEXT"
        }

    return textresult

