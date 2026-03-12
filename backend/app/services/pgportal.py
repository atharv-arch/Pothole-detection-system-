# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — PG Portal Selenium Filing (Production)
# Section 9: Automated grievance filing on pgportal.gov.in
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from app.config import settings
from app.services.s3 import s3_download_temp, s3_upload

logger = logging.getLogger("apis.pgportal")


def file_on_pgportal(complaint: dict) -> str:
    """
    Automate grievance filing on pgportal.gov.in using Selenium.

    Steps:
        1. Load portal and log in
        2. Solve CAPTCHA via 2captcha
        3. Navigate to Lodge Grievance
        4. Select Ministry (MoRTH) and Department (NHAI)
        5. Fill grievance text (complaint letter, max 3000 chars)
        6. Fill system identity details
        7. Upload PDF attachment
        8. Submit and capture reference number
        9. Screenshot confirmation as proof

    Args:
        complaint: dict with letter text, PDF S3 URL, highway info

    Returns:
        PG Portal reference number string

    Raises:
        RuntimeError: if credentials not configured
        Exception: on filing failure (retried by Celery)
    """
    if not settings.PGPORTAL_USER or not settings.PGPORTAL_PASS:
        raise RuntimeError(
            "PGPORTAL_USER/PASS not set — cannot file grievance"
        )

    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new")

    driver = uc.Chrome(options=options)
    wait = WebDriverWait(driver, 20)
    complaint_id = complaint.get("complaint_id", "UNKNOWN")

    try:
        # Step 1 — Load portal and log in
        driver.get("https://pgportal.gov.in/")
        wait.until(
            EC.element_to_be_clickable((By.LINK_TEXT, "Login"))
        ).click()

        wait.until(
            EC.presence_of_element_located((By.ID, "userId"))
        ).send_keys(settings.PGPORTAL_USER)

        driver.find_element(By.ID, "password").send_keys(settings.PGPORTAL_PASS)

        # Step 2 — CAPTCHA
        captcha_img = driver.find_element(By.ID, "captchaImage")
        captcha_b64 = captcha_img.screenshot_as_base64

        captcha_code = _solve_captcha(captcha_b64)
        driver.find_element(By.ID, "captchaInput").send_keys(captcha_code)
        driver.find_element(By.ID, "loginBtn").click()

        wait.until(EC.url_contains("/Home"))

        # Step 3 — Navigate to Lodge Grievance
        wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//a[contains(text(),'Lodge Grievance')]")
            )
        ).click()
        wait.until(EC.presence_of_element_located((By.ID, "grievanceForm")))

        # Step 4 — Select Ministry & Department
        Select(driver.find_element(By.ID, "ministry")).select_by_visible_text(
            "Ministry of Road Transport and Highways"
        )
        time.sleep(1)  # wait for AJAX
        Select(driver.find_element(By.ID, "department")).select_by_visible_text(
            "National Highways Authority of India"
        )

        # Step 5 — Grievance text (max 3000 chars)
        grievance_text = complaint.get("letter", "")[:3000]
        driver.find_element(By.ID, "grievanceText").send_keys(grievance_text)

        # Step 6 — System identity details
        driver.find_element(By.ID, "name").clear()
        driver.find_element(By.ID, "name").send_keys(
            "APIS Automated Monitor — CHIPS"
        )
        driver.find_element(By.ID, "address").send_keys(
            f"{complaint.get('highway_id', 'NH-30')}, "
            f"KM {complaint.get('km_marker', 'N/A')}, Chhattisgarh"
        )
        if settings.SYSTEM_PHONE:
            driver.find_element(By.ID, "mobile").send_keys(settings.SYSTEM_PHONE)
        if settings.SYSTEM_EMAIL:
            driver.find_element(By.ID, "email").send_keys(settings.SYSTEM_EMAIL)

        # Step 7 — Upload PDF
        if complaint.get("pdf_s3_url"):
            local_pdf = s3_download_temp(complaint["pdf_s3_url"])
            file_input = driver.find_element(
                By.CSS_SELECTOR, "input[type='file']"
            )
            file_input.send_keys(local_pdf)
            time.sleep(2)

        # Step 8 — Submit
        driver.find_element(By.ID, "submitGrievance").click()

        # Step 9 — Capture reference number
        ref_el = wait.until(
            EC.presence_of_element_located((By.ID, "registrationNumber"))
        )
        reference_number = ref_el.text.strip()

        # Step 10 — Screenshot
        screenshot_path = os.path.join(
            os.environ.get("TEMP", "/tmp"),
            f"{complaint_id}_confirmation.png",
        )
        driver.save_screenshot(screenshot_path)
        s3_upload(
            screenshot_path,
            f"filings/{complaint_id}_confirmation.png",
        )

        logger.info(
            "PG Portal filed: %s → ref=%s", complaint_id, reference_number
        )
        return reference_number

    except Exception as e:
        logger.error("PG Portal filing failed: %s", e)
        # Save error screenshot
        try:
            err_path = os.path.join(
                os.environ.get("TEMP", "/tmp"),
                f"{complaint_id}_error.png",
            )
            driver.save_screenshot(err_path)
            s3_upload(err_path, f"filings/{complaint_id}_error.png")
        except Exception:
            pass
        raise
    finally:
        driver.quit()


def _solve_captcha(captcha_base64: str) -> str:
    """Solve CAPTCHA using 2captcha service."""
    if not settings.TWO_CAPTCHA_API_KEY:
        raise RuntimeError("TWO_CAPTCHA_API_KEY not set — cannot solve CAPTCHA")

    import twocaptcha

    solver = twocaptcha.TwoCaptcha(settings.TWO_CAPTCHA_API_KEY)
    result = solver.normal(captcha_base64)
    return result["code"]


def fallback_email_complaint(complaint: dict) -> None:
    """
    Fallback: send complaint via email when PG Portal filing fails
    after max retries.
    """
    import smtplib
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not settings.SYSTEM_EMAIL or not settings.SYSTEM_EMAIL_PASS:
        logger.error("SYSTEM_EMAIL not configured — cannot send fallback email")
        return

    msg = MIMEMultipart()
    msg["Subject"] = complaint.get("metadata", {}).get(
        "subject_line", "Pothole Complaint — APIS"
    )
    msg["From"] = settings.SYSTEM_EMAIL
    msg["To"] = _get_division_engineer_email(complaint.get("highway_id", "NH-30"))

    # Body
    body = complaint.get("letter", "See attached complaint letter.")
    msg.attach(MIMEText(body, "plain"))

    # Attach PDF
    if complaint.get("pdf_s3_url"):
        try:
            local_pdf = s3_download_temp(complaint["pdf_s3_url"])
            with open(local_pdf, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{complaint.get("complaint_id", "complaint")}.pdf"',
                )
                msg.attach(part)
        except Exception as e:
            logger.warning("Failed to attach PDF: %s", e)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.SYSTEM_EMAIL, settings.SYSTEM_EMAIL_PASS)
            server.sendmail(msg["From"], msg["To"], msg.as_string())
        logger.info("Fallback email sent for %s", complaint.get("complaint_id"))
    except Exception as e:
        logger.error("Fallback email failed: %s", e)


def _get_division_engineer_email(highway_id: str) -> str:
    """Map highway to division engineer email (placeholder until NHAI directory)."""
    return settings.SYSTEM_EMAIL or "grievance@nhai.org"
