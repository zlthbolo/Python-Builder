FROM python:3.12-slim
WORKDIR /app
COPY campus-community-finder/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY campus-community-finder/*.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["python", "app.py"]
