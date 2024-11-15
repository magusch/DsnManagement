FROM python:3.11
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /dsn_django
COPY requirements.txt /dsn_django/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
ADD . /dsn_django
# RUN python manage.py makemigrations
RUN python manage.py migrate
RUN python manage.py collectstatic --noinput