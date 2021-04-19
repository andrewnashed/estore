import smtplib
from dotenv import load_dotenv
import os
load_dotenv(".env")
my_email = os.getenv("FROM_EMAIL")
password = os.getenv("PASSWORD")
to_email = os.getenv("TO_EMAIL")


def send_email(name, email, message):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as connection:
        connection.login(user=my_email, password=password)
        connection.sendmail(from_addr=my_email,
                            to_addrs=to_email,
                            msg=f"Subject:hello\n\n Name:{name}\nEmail:{email}\nMessage:{message}")
