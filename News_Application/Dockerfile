# Use official Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /code

# System dependencies needed to build mysqlclient / mariadb connector,
# plus mysqladmin (used by docker-compose.yml to wait for the db service)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    default-mysql-client \
    pkg-config \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt /code/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project
COPY . /code/

# Document the port the app listens on
EXPOSE 8000

# Default command if the container is run standalone
# (docker-compose.yml overrides this with its own `command:`)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]