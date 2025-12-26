FROM mcr.microsoft.com/dotnet/sdk:10.0

# Install Python 3 and git
RUN apt-get update && \
  apt-get install -y python3 python3-pip git && \
  rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt --break-system-packages

WORKDIR /app
