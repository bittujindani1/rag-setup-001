# Use an official Python runtime as a parent image
FROM python:3.11.4

# Set the working directory in the container
WORKDIR /app

# Copy only the requirements file first to leverage caching for dependencies
COPY requirements.txt /app/requirements.txt

# Install dependencies before copying the rest of the application files
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copy the rest of the app's code
COPY . /app

EXPOSE 8000

# Run app.py when the container launches
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
