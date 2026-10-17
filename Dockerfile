FROM python:3.15.0-slim

# Set the working directory in the container
WORKDIR /app

# Ensure Python output is sent straight to container logs without buffering
ENV PYTHONUNBUFFERED=1

# Copy the requirements file into the container
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Command to run the application
CMD ["python", "connection_bot.py"]
