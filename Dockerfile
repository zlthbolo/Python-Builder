FROM python:3.12-slim
WORKDIR /app
COPY campus-community-finder/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY campus-community-finder/*.py ./
COPY campus-community-finder/mbzuai_discussions.json ./mbzuai_discussions.json
ENV PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["python", "app.py"]
