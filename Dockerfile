FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
RUN pip install --upgrade pip && pip install '.[vectors]'
USER app
EXPOSE 8000
CMD ["uvicorn", "mutual_fund_agent_analysis.main:app", "--host", "0.0.0.0", "--port", "8000"]
