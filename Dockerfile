FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ponytail: multi-stage build (separate builder for compiling deps) only
# pays off once image size or build time actually hurts — not a day-1
# concern for an MVP with this dependency list.
