FROM python:3-alpine


WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application script
COPY main.py .

# Run the script
CMD ["python", "-u", "main.py"]

