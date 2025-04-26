from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    InvalidSessionIdException,
)
from faker import Faker
# OTHER Libraries for Robust usage
import asyncio
import platform
import uuid
import re
import random
import time
import logging
import os
from contextlib import contextmanager

# Configuration
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "C:\\Users\\HP\\OneDrive\\Desktop\\chromedriver.exe")
FORM_URL = "https://forms.office.com/r/VxWggscai0"
MAX_PAGES = 10
MAX_RETRIES = 8
DEFAULT_WAIT_TIMEOUT = 60
FIELD_INTERACTION_DELAY = (0.2, 0.5)

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# Faker Initialization
fake = Faker()

# Sample Data (IGNORE THESE.)
sample_contacts = [
    {"name": "John Doe", "email": "john.doe@example.com", "phone": "1234567890"},
    {"name": "Jane Smith", "email": "jane.smith@example.com", "phone": "0987654321"},
]
sample_companies = ["Acme Corp", "Globex Inc", "Initech"]
sample_project_titles = ["Project Alpha", "Initiative Beta", "Program Gamma"]
sample_texts = [
    "This is a sample response for a generic question.",
    "Our team is committed to delivering high-quality outcomes.",
    "The project aligns with strategic organizational goals.",
]

# Field Type Detection and Value Generation
def get_field_data(label_text=""):
    label = label_text.lower()
    contact = random.choice(sample_contacts)

    if "measurable impact" in label:
        return (
            "This project will generate measurable impact by addressing a clearly defined need within the target "
            "community. It will implement evidence-based strategies with tracked outcomes using pre- and post-"
            "assessments, surveys, and key performance indicators. These insights will inform continuous improvement.",
            "long_text"
        )
    elif "success indicator" in label or "key success" in label:
        return (
            "Key success indicators include the number of individuals reached, measurable improvement in outcomes, "
            "participant satisfaction, and timely delivery of milestones. Stakeholder engagement will also be tracked.",
            "long_text"
        )
    elif "name" in label:
        return contact["name"], "name"
    elif "email" in label:
        return contact["email"], "email"
    elif "phone" in label:
        phone = contact.get("phone", fake.phone_number())
        phone = re.sub(r"[^0-9\-]", "", phone)
        phone = re.sub(r"x\d+", "", phone).strip()
        return phone, "phone"
    elif "organization" in label or "institution" in label or "company" in label:
        return random.choice(sample_companies), "company"
    elif "project title" in label:
        return random.choice(sample_project_titles), "project_title"
    elif "date" in label:
        return fake.date(pattern="%Y-%m-%d"), "date"
    else:
        return random.choice(sample_texts), "generic"

# Helper Functions
def find_label_for_element(driver, element):
    label_text = "Unknown Label"
    try:
        label_ids = element.get_attribute("aria-labelledby")
        if label_ids:
            label_elem = driver.find_element(By.ID, label_ids.split()[0])
            label_text = label_elem.text.strip()
            if label_text:
                return label_text

        element_id = element.get_attribute("id")
        if element_id:
            label_elem = driver.find_element(By.XPATH, f"//label[@for='{element_id}']")
            label_text = label_elem.text.strip()
            if label_text:
                return label_text

        question_container = element.find_element(
            By.XPATH, "./ancestor::div[contains(@data-automation-id, 'questionItem')]"
        )
        label_elem = question_container.find_element(
            By.CSS_SELECTOR, "span[data-automation-id='questionTitle']"
        )
        label_text = label_elem.text.strip()
        if label_text:
            return label_text

        aria_label = element.get_attribute("aria-label")
        if aria_label:
            label_text = aria_label.strip()
            if label_text:
                return label_text

    except NoSuchElementException:
        if element.get_attribute("type") == "radio":
            try:
                choice_label = element.find_element(
                    By.XPATH,
                    "./following-sibling::*//span | ./following-sibling::*//label | ./parent::span/following-sibling::span",
                )
                label_text = choice_label.text.strip()
                if label_text:
                    return f"Radio Option: {label_text}"
            except NoSuchElementException:
                pass
    except Exception as e:
        logging.warning(f"Label finding error: {e}")

    logging.warning(f"Could not find label for element: {element.get_attribute('outerHTML')[:100]}...")
    return label_text

def try_interact_field(field, action, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            action(field)
            return True
        except (StaleElementReferenceException, ElementClickInterceptedException):
            logging.warning(f"Stale element or click intercepted on attempt {attempt+1}, retrying...")
            time.sleep(0.5)
    logging.error(f"Failed to interact with field after {max_attempts} attempts.")
    return False

def wait_for_overlays_to_disappear(driver, wait):
    try:
        wait.until(
            EC.invisibility_of_element_located(
                (By.XPATH, '//div[contains(@class, "overlay") or contains(@class, "spinner")]')
            )
        )
    except TimeoutException:
        logging.debug("No overlays detected or they persisted.")

@contextmanager
def setup_webdriver():
    service = Service(executable_path=CHROMEDRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("detach", True)

    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        yield driver
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logging.warning(f"Error quitting driver: {e}")

# Main Form Automation
def automate_form(driver):
    wait = WebDriverWait(driver, DEFAULT_WAIT_TIMEOUT)
    page_number = 1
    total_filled = 0
    question_counter = 0
    navigation_retries = 0
    previous_visible_field_ids = set()
    previous_question_titles = set()
    validation_error_detected = False

    driver.get(FORM_URL)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    logging.info(f"Form page loaded: {FORM_URL}")

    try:
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        logging.info("JavaScript document ready state: complete")
    except TimeoutException:
        logging.warning("Document ready state not complete within timeout")

    try:
        consent_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    '//button[contains(text(), "Accept") or contains(text(), " Agree") or @data-testid="cookie-accept-button"]',
                )
            )
        )
        driver.execute_script("arguments[0].click();", consent_button)
        logging.info("Accepted consent banner")
        time.sleep(0.5)
    except TimeoutException:
        logging.info("No consent banner detected")

    while page_number <= MAX_PAGES:
        logging.info(f"--- Processing Page {page_number} ---")
        time.sleep(1)

        try:
            question_containers = wait.until(
                EC.visibility_of_all_elements_located(
                    (By.XPATH, '//div[contains(@data-automation-id, "questionItem")]')
                )
            )
            logging.info(f"Found {len(question_containers)} question containers")
        except TimeoutException:
            logging.error("Form questions not found on page")
            return False, "Form questions not found on page"

        try:
            text_inputs = driver.find_elements(
                By.XPATH,
                '//input[@type="text" or @type="email" or @type="tel" or @type="number" or @type="search" or contains(@aria-label, "Text") or contains(@data-automation-id, "textInput")]',
            )
            text_areas = driver.find_elements(
                By.XPATH, '//textarea | //div[@contenteditable="true"]'
            )
            all_text_fields = text_inputs + text_areas
            dropdowns = driver.find_elements(
                By.XPATH, '//select | //div[@role="combobox"] | //div[contains(@class, "dropdown")]'
            )
            radio_buttons = driver.find_elements(
                By.XPATH, '//input[@type="radio"] | //div[@role="radio"]'
            )
            checkboxes = driver.find_elements(
                By.XPATH, '//input[@type="checkbox"] | //div[@role="checkbox"]'
            )
            date_fields = driver.find_elements(
                By.XPATH, '//input[@type="date" or @type="datetime-local" or contains(@aria-label, "Date")]'
            )
            fallback_inputs = driver.find_elements(
                By.XPATH, '//input[not(@type="hidden") and not(@type="submit") and not(@type="button")]'
            )
            all_text_fields.extend([f for f in fallback_inputs if f not in all_text_fields])
        except InvalidSessionIdException:
            logging.error("Browser session lost during field detection")
            raise
        except Exception as e:
            logging.error(f"Error detecting fields: {e}")
            continue

        all_fields = all_text_fields + dropdowns + radio_buttons + checkboxes + date_fields
        logging.info(
            f"Found {len(all_text_fields)} text fields, {len(dropdowns)} dropdowns, "
            f"{len(radio_buttons)} radios, {len(checkboxes)} checkboxes, {len(date_fields)} date fields."
        )

        if not all_fields:
            logging.warning("No fields detected. Logging page source for debugging.")
            with open(f"page_source_page_{page_number}.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logging.info(f"Page source saved to page_source_page_{page_number}.html")

        current_visible_field_ids = set()
        current_question_titles = set()
        for field in all_fields:
            try:
                if field.is_displayed() and field.is_enabled():
                    field_id = (
                        field.get_attribute("id")
                        or field.get_attribute("name")
                        or field.get_attribute("aria-labelledby")
                        or field.get_attribute("data-automation-id")
                        or ""
                    )
                    if field_id:
                        current_visible_field_ids.add(field_id)
            except StaleElementReferenceException:
                continue

        try:
            for container in question_containers:
                try:
                    title_elem = container.find_element(
                        By.CSS_SELECTOR, "span[data-automation-id='questionTitle']"
                    )
                    title_text = title_elem.text.strip()
                    if title_text:
                        current_question_titles.add(title_text)
                except NoSuchElementException:
                    continue
        except Exception as e:
            logging.warning(f"Error collecting question titles: {e}")

        if (
            page_number > 1
            and current_visible_field_ids
            and current_visible_field_ids == previous_visible_field_ids
            and current_question_titles == previous_question_titles
            and not validation_error_detected
        ):
            logging.warning(
                f"Possible stuck page (retry {navigation_retries+1}/{MAX_RETRIES}). "
                f"Field IDs: {current_visible_field_ids}"
            )
            try:
                next_button = driver.find_element(
                    By.XPATH,
                    '//button[contains(@data-automation-id, "nextButton") or contains(@aria-label, "Next") or contains(text(), "Next") or contains(@class, "next")][not(@disabled)]',
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", next_button)
                logging.info("Retried clicking 'Next' button to resolve stuck page.")
                time.sleep(1)
            except Exception as e:
                logging.warning(f"Failed to retry 'Next' button click: {e}")

            navigation_retries += 1
            if navigation_retries >= MAX_RETRIES:
                logging.error("Stuck on the same page after retries.")
                return False, "Stuck on the same page after retries"
        else:
            navigation_retries = 0
            previous_visible_field_ids = current_visible_field_ids
            previous_question_titles = current_question_titles

        for i, field in enumerate(all_text_fields):
            try:
                if not field.is_displayed() or not field.is_enabled():
                    continue
                if field.get_attribute("value") or (field.tag_name == "div" and field.text.strip()):
                    continue
                label_text = find_label_for_element(driver, field)
                data, field_type = get_field_data(label_text)
                def fill_action(f):
                    if f.tag_name == "div":
                        driver.execute_script("arguments[0].innerText = arguments[1];", f, data)
                    else:
                        f.clear()
                        f.send_keys(data)
                if try_interact_field(field, fill_action):
                    logging.info(f"  [{field_type}] Filled '{label_text}' -> '{data[:50]}...'")
                    total_filled += 1
                    question_counter += 1
                    time.sleep(random.uniform(*FIELD_INTERACTION_DELAY))
            except Exception as e:
                logging.warning(f"Error filling text field {i+1} ('{label_text}'): {e}")

        for i, dropdown in enumerate(dropdowns):
            try:
                if not dropdown.is_displayed() or not dropdown.is_enabled():
                    continue
                label_text = find_label_for_element(driver, dropdown)
                if dropdown.tag_name == "select":
                    select = Select(dropdown)
                    options = [opt for opt in select.options if opt.is_enabled() and opt.get_attribute("value")]
                    if options:
                        random_option = random.choice(options)
                        select.select_by_visible_text(random_option.text)
                        logging.info(f"  Selected dropdown '{label_text}': {random_option.text}")
                        total_filled += 1
                        question_counter += 1
                    else:
                        logging.warning(f"  No valid options for dropdown '{label_text}'")
                else:
                    driver.execute_script("arguments[0].click();", dropdown)
                    options = driver.find_elements(By.XPATH, '//div[@role="option"]')
                    if options:
                        random.choice(options).click()
                        logging.info(f"  Selected custom combobox '{label_text}'")
                        total_filled += 1
                        question_counter += 1
                time.sleep(random.uniform(*FIELD_INTERACTION_DELAY))
            except Exception as e:
                logging.warning(f"Error with dropdown {i+1} ('{label_text}'): {e}")

        radio_groups = {}
        for radio in radio_buttons:
            try:
                name = radio.get_attribute("name")
                if name:
                    radio_groups.setdefault(name, []).append(radio)
            except StaleElementReferenceException:
                continue

        for group_name, radios in radio_groups.items():
            try:
                question_label = find_label_for_element(driver, radios[0])
                logging.info(f"Processing radio group: '{question_label}' (name={group_name})")
                valid_radios = [r for r in radios if r.is_displayed() and r.is_enabled()]
                if not valid_radios:
                    logging.warning(f"No valid radios in group '{question_label}'")
                    if validation_error_detected:
                        valid_radios = radios
                        logging.info(f"Validation error detected, attempting all radios in group '{question_label}'")
                    else:
                        continue

                if any(r.get_attribute("aria-checked") == "true" for r in valid_radios):
                    logging.info(f"Radio group '{question_label}' already selected")
                    continue

                yes_radio = None
                no_radio = None
                for radio in valid_radios:
                    try:
                        label_id = radio.get_attribute("aria-labelledby")
                        choice_label = (
                            driver.find_element(By.ID, label_id).text.strip().lower()
                            if label_id
                            else find_label_for_element(driver, radio).lower()
                        )
                        if "yes" in choice_label:
                            yes_radio = radio
                        elif "no" in choice_label:
                            no_radio = radio
                    except NoSuchElementException:
                        continue

                is_sixth_question = False
                try:
                    for radio in valid_radios:
                        if driver.find_elements(By.XPATH, f'//*[@id="question-list"]/div[6]/div[2]/div//input[@name="{group_name}"]'):
                            is_sixth_question = True
                            break
                except Exception as e:
                    logging.warning(f"Error checking XPath for 6th question: {e}")

                if is_sixth_question and yes_radio:
                    selected_radio = yes_radio
                    logging.info(f"Special handling: Selecting 'Yes' for 6th question radio group '{question_label}'")
                else:
                    if "previous funding" in question_label.lower() or question_counter in range(12, 15):
                        logging.info(f"Handling special question: '{question_label}' (counter={question_counter})")
                        selected_radio = yes_radio or no_radio or random.choice(valid_radios)
                    else:
                        selected_radio = (
                            yes_radio
                            if yes_radio and ("implemented" in question_label.lower() or "agree" in question_label.lower())
                            else random.choice([yes_radio, no_radio]) if yes_radio and no_radio
                            else random.choice(valid_radios)
                        )

                def click_radio(r):
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", r)
                    try:
                        label_id=r.get_attribute("aria-labelledby")
                        if label_id:
                            label_elem = driver.find_element(By.ID, label_id)
                            driver.execute_script("arguments[0].click();", label_elem)
                        else:
                            # Fallback: click on the nearest label ancestor or contanier
                            parent_label = r.find_element(By.XPATH, "./ancestor::label")
                            driver.execute_script("arguments[0].click();" ,parent_label)
                    except Exception as e:
                        logging.warning(f"Failed to click via label for radio: {e}")
                        raise
                    
                    time.sleep(0.1)
                    if r.get_attribute("aria-checked") !='true':
                        raise Exception("Radio button click did not register")
                if not try_interact_field(selected_radio, click_radio):
                    try:
                        label_id = selected_radio.get_attribute("aria-labelledby")
                        if label_id:
                            label_elem = driver.find_element(By.ID, label_id)
                            driver.execute_script("arguments[0].click();", label_elem)
                        else:
                            parent = selected_radio.find_element(
                                By.XPATH, "./ancestor::div[contains(@class, 'choice') or contains(@role, 'radio')]"
                            )
                            driver.execute_script("arguments[0].click();", parent)
                        time.sleep(0.1)
                        if selected_radio.get_attribute("aria-checked") != "true":
                            logging.warning(f"Failed to select radio in group '{question_label}'")
                            continue
                    except Exception as e:
                        logging.warning(f"Error clicking label/parent for radio in group '{question_label}'): {e}")
                        continue

                selected_value = selected_radio.get_attribute("value")
                try:
                    label_id = selected_radio.get_attribute("aria-labelledby")
                    if label_id:
                        selected_value = driver.find_element(By.ID, label_id).text.strip()
                except NoSuchElementException:
                    pass
                logging.info(f"  Selected radio in group '{question_label}': '{selected_value}'")
                total_filled += 1
                question_counter += 1
                time.sleep(random.uniform(*FIELD_INTERACTION_DELAY))
            except Exception as e:
                logging.error(f"Error with radio group '{group_name}' ('{question_label}'): {e}")

        checkbox_groups = {}
        for checkbox in checkboxes:
            try:
                name = checkbox.get_attribute("name")
                if name:
                    checkbox_groups.setdefault(name, []).append(checkbox)
            except StaleElementReferenceException:
                continue

        for group_name, checkboxes_in_group in checkbox_groups.items():
            try:
                question_label = find_label_for_element(driver, checkboxes_in_group[0])
                logging.info(f"Processing checkbox group: '{question_label}' (name={group_name})")
                valid_checkboxes = [cb for cb in checkboxes_in_group if cb.is_displayed() and cb.is_enabled()]
                if not valid_checkboxes:
                    logging.warning(f"No valid checkboxes in group '{question_label}'")
                    if validation_error_detected:
                        valid_checkboxes = checkboxes_in_group
                        logging.info(f"Validation error detected, attempting all checkboxes in group '{question_label}'")
                    else:
                        continue

                if validation_error_detected:
                    selected_checkboxes = valid_checkboxes
                    logging.info(f"Validation error detected, selecting all checkboxes in group '{question_label}'")
                else:
                    num_to_select = random.randint(1, len(valid_checkboxes))
                    selected_checkboxes = random.sample(valid_checkboxes, num_to_select)

                for cb in selected_checkboxes:
                    if cb.get_attribute("aria-checked") == "true":
                        continue
                    def click_checkbox(c):
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", c)
                        driver.execute_script("arguments[0].click();", c)
                        time.sleep(0.1)
                        if c.get_attribute("aria-checked") != "true":
                            raise Exception("Checkbox click did not register")

                    if try_interact_field(cb, click_checkbox):
                        logging.info(f"  Selected checkbox in group '{question_label}'")
                        total_filled += 1
                        question_counter += 1
                    else:
                        logging.warning(f"Failed to select checkbox in group '{question_label}'")
                    time.sleep(random.uniform(*FIELD_INTERACTION_DELAY))
            except Exception as e:
                logging.error(f"Error with checkbox group '{group_name}' ('{question_label}'): {e}")

        for i, date_field in enumerate(date_fields):
            try:
                if not date_field.is_displayed() or not date_field.is_enabled() or date_field.get_attribute("value"):
                    continue
                label_text = find_label_for_element(driver, date_field)
                date_value = fake.date(pattern="%Y-%m-%d")
                def fill_date(f):
                    f.clear()
                    f.send_keys(date_value)
                if try_interact_field(date_field, fill_date):
                    logging.info(f"  Filled date field '{label_text}': {date_value}")
                    total_filled += 1
                    question_counter += 1
                    time.sleep(random.uniform(*FIELD_INTERACTION_DELAY))
            except Exception as e:
                logging.warning(f"Error filling date field {i+1} ('{label_text}'): {e}")

        logging.info(f"--- Total Questions Interacted With So Far: {total_filled} ---")

        validation_error_detected = False
        try:
            errors = driver.find_elements(
                By.XPATH, '//*[contains(@class, "error") or contains(text(), "required") or contains(text(), "invalid")]'
            )
            for error in errors:
                if error.is_displayed():
                    try:
                        error_container = error.find_element(By.XPATH, "./ancestor::div[contains(@data-automation-id, 'questionItem')]")
                        error_label = error_container.find_element(By.CSS_SELECTOR, "span[data-automation-id='questionTitle']").text.strip()
                        logging.error(f"Validation error for question '{error_label}': {error.text}")
                    except NoSuchElementException:
                        logging.error(f"Validation error detected: {error.text}")
                    validation_error_detected = True
                    with open(f"validation_error_page_{page_number}.html", "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    logging.info(f"Page source saved to validation_error_page_{page_number}.html")
        except Exception as e:
            logging.warning(f"Error checking validation messages: {e}")

        logging.info("--- Checking for Submit Button ---")
        try:
            submit_button = driver.find_element(
                By.XPATH,
                '//button[contains(@data-automation-id, "submitButton") or contains(@aria-label, "Submit") or contains(text(), "Submit")][not(@disabled)]',
            )
            logging.info("Submit button found, attempting to submit form.")
            driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", submit_button)
            try:
                wait.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            '//*[contains(text(), "Your response was submitted") or contains(text(), "Thanks")]',
                        )
                    )
                )
                logging.info("--- Form Submitted Successfully ---")
                return True, "Form submitted successfully."
            except TimeoutException:
                logging.warning("Submission attempted but no confirmation message found, continuing.")
        except NoSuchElementException:
            logging.info("No Submit button found on this page, attempting Next.")
        except Exception as e:
            logging.error(f"Error attempting to click Submit button: {e}")

        logging.info("--- Attempting Navigation ---")
        wait_for_overlays_to_disappear(driver, wait)

        try:
            next_button = wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//button[contains(@data-automation-id, "nextButton") or contains(@aria-label, "Next") or contains(text(), "Next") or contains(@class, "next")][not(@disabled)]',
                    )
                )
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", next_button)
            wait.until(
                lambda d: (
                    EC.staleness_of(next_button)(d)
                    or EC.presence_of_element_located(
                        (By.XPATH, '//div[contains(@data-automation-id, "questionItem")]')
                    )(d)
                )
            )
            page_number += 1
            continue

        except TimeoutException:
            logging.info("'Next' button not found, rechecking 'Submit'.")
            try:
                submit_button = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            '//button[contains(@data-automation-id, "submitButton") or contains(@aria-label, "Submit") or contains(text(), "Submit")][not(@disabled)]',
                        )
                    )
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", submit_button)
                wait.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            '//*[contains(text(), "Your response was submitted") or contains(text(), "Thanks")]',
                        )
                    )
                )
                logging.info("--- Form Submitted Successfully ---")
                return True, "Form submitted successfully."
            except TimeoutException:
                logging.error("Neither 'Next' nor 'Submit' found.")
                return False, "Navigation failed: No 'Next' or 'Submit' button found."
            except Exception as e:
                logging.error(f"Error clicking Submit button: {e}")
                raise

        except ElementClickInterceptedException:
            logging.error("'Next' button click intercepted.")
            return False, "ElementClickInterceptedException while clicking Next."

        except Exception as e:
            logging.error(f"Error clicking Next button: {e}")
            raise

    logging.error(f"Reached maximum pages ({MAX_PAGES}) without submitting form.")
    return False, f"Reached maximum pages ({MAX_PAGES}) without submitting form."

def run_selenium_with_input(user_data):
    global sample_contacts, sample_companies, sample_project_titles

    # Update sample data with user-provided input from Form.html
    sample_contacts = [
        {
            "name": user_data.get("fullName", random.choice(sample_contacts)["name"]),
            "email": user_data.get("email", random.choice(sample_contacts)["email"]),
            "phone": user_data.get("phone", fake.phone_number()),
        }
    ]
    sample_companies = [user_data.get("company", random.choice(sample_companies))]
    sample_project_titles = [user_data.get("projectTitle", random.choice(sample_project_titles))]

    with setup_webdriver() as driver:
        try:
            success, message = automate_form(driver)
            return success, message
        except Exception as e:
            logging.error(f"Form automation failed: {e}", exc_info=True)
            return False, str(e)

# Example usage
if __name__ == "__main__":
    user_data = {
        "fullName": "Alice Johnson",
        "email": "alice.johnson@example.com",
        "phone": "1234567890",
        "company": "Tech Innovations",
        "projectTitle": "Smart City Initiative",
    }
    success, message = run_selenium_with_input(user_data)
    logging.info(f"Result: {'Success' if success else 'Failed'}, Message: {message}")

