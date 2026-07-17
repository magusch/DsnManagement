FROM python:3.11
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /dsn_django
COPY requirements.txt /dsn_django/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
ADD . /dsn_django

RUN python manage.py showmigrations || true

RUN python manage.py migrate --noinput || \
    (echo "T --fake-initial for existing DB..." && \
     python manage.py migrate --fake-initial --noinput && \
     echo "✅ Migration was accepted with --fake-initial") || \
    (echo "❌ Critical migration error" && \
     exit 1)
     
RUN python manage.py collectstatic --noinput