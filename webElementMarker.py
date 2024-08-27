import json
import os
import shutil
import time
from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions


def create_directories():
    if not os.path.exists('screenshots'):
        os.makedirs('screenshots')
    if not os.path.exists('marked_screenshots'):
        os.makedirs('marked_screenshots')


create_directories()


def init_driver():
    driver = None
    with open('config.json') as config_file:
        config = json.load(config_file)

    if config['browser_type'] == "Edge":
        options = EdgeOptions()
        options.add_argument('--ignore-certificate-errors')
        driver = webdriver.Edge(options=options)
    elif config['browser_type'] == "Chrome":
        options = ChromeOptions()
        options.add_argument('--ignore-certificate-errors')
        driver = webdriver.Chrome(options=options)

    driver.maximize_window()
    return driver


driver = init_driver()


def login(driver):
    with open('config.json') as config_file:
        config = json.load(config_file)

    if config['login_required']:
        driver.get(config["login_url"])
        time.sleep(2)
        username = driver.find_element(By.ID, config['username_element'])
        password = driver.find_element(By.XPATH, config['password_element'])
        username.send_keys(config['username'])
        password.send_keys(config['password'])
        driver.find_element(By.ID, config['login_button_element']).click()
        time.sleep(2)


login(driver)

with open('pages.json') as pages_file:
    pages = json.load(pages_file)

previous_data = {}
if os.path.exists('previous_data.json'):
    with open('previous_data.json', encoding="utf-8") as previous_file:
        previous_data = json.load(previous_file)

changes = {}

for page_index, (page_url, page_info) in enumerate(pages.items(), start=1):
    driver.get(page_url)
    time.sleep(2)

    screenshot_path = f'screenshots/screenshot_{page_index}.png'
    driver.save_screenshot(screenshot_path)

    driver.execute_script("""
    window.getXPath = function(element) {
        if (element.id !== '') {
            return 'id("' + element.id + '")';
        }
        if (element.tagName === 'HTML') {
            return '/' + element.tagName.toLowerCase();
        }
        if (element === document.body) {
            return '/html/body';
        }

        var ix = 0;
        var siblings = element.parentNode.childNodes;
        for (var i = 0; i < siblings.length; i++) {
            var sibling = siblings[i];
            if (sibling === element) {
                return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
            }
            if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                ix++;
            }
        }
    }
    """)

    elements = driver.find_elements(By.XPATH,
                                    '//button | //input | //textarea | //select | //p-dropdown | //p-inputtext')
    current_elements_info = {}

    for element in elements:
        element_xpath = driver.execute_script("return getXPath(arguments[0]);", element)
        element_info = {
            "type": element.get_attribute('type'),
            "id": element.get_attribute('id'),
            "name": element.get_attribute('name'),
            "className": element.get_attribute('class'),
            "text": element.get_attribute('outerText'),
            "xpath": element_xpath,
            "location": element.location,
            "size": element.size
        }
        current_elements_info[element_xpath] = element_info

    previous_elements_info = previous_data.get(page_url, {})
    page_changes = {"added": {}, "removed": {}, "modified": {}}

    for xpath, info in current_elements_info.items():
        if xpath not in previous_elements_info:
            page_changes["added"][xpath] = info
        elif info != previous_elements_info[xpath]:
            page_changes["modified"][xpath] = {
                "previous": previous_elements_info[xpath],
                "current": info
            }

    for xpath, info in previous_elements_info.items():
        if xpath not in current_elements_info:
            page_changes["removed"][xpath] = info

    if any(page_changes.values()):
        changes[page_url] = {
            "page_name": page_url,
            "changes": page_changes}

    previous_data[page_url] = current_elements_info

    for button_index, button_info in enumerate(page_info.get("form_buttons", []), start=1):
        try:
            button = driver.find_element(By.XPATH, button_info['xpath'])
            button.click()
            time.sleep(2)

            form_screenshot_path = f'screenshots/screenshot_{page_index}_{button_index}_form.png'
            driver.save_screenshot(form_screenshot_path)

            form_elements = driver.find_elements(By.XPATH, '//button | //input | //textarea | //select | //p-dropdown')
            form_elements_info = {}

            for form_element in form_elements:
                form_element_xpath = driver.execute_script("return getXPath(arguments[0]);", form_element)
                form_element_info = {
                    "type": form_element.get_attribute('type'),
                    "id": form_element.get_attribute('id'),
                    "name": form_element.get_attribute('name'),
                    "className": form_element.get_attribute('class'),
                    "text": form_element.get_attribute('outerText'),
                    "xpath": form_element_xpath,
                    "location": form_element.location,
                    "size": form_element.size
                }
                form_elements_info[form_element_xpath] = form_element_info

            previous_form_elements_info = previous_data.get(f'{page_url}_form', {})
            form_changes = {"added": {}, "removed": {}, "modified": {}}

            for xpath, info in form_elements_info.items():
                if xpath not in previous_form_elements_info:
                    form_changes["added"][xpath] = info
                elif info != previous_form_elements_info[xpath]:
                    form_changes["modified"][xpath] = {
                        "previous": previous_form_elements_info[xpath],
                        "current": info
                    }

            for xpath, info in previous_form_elements_info.items():
                if xpath not in form_elements_info:
                    form_changes["removed"][xpath] = info

            if any(form_changes.values()):
                changes[f'{page_url}_form'] = {
                    "page_name": page_url,
                    "form_changes": form_changes}

            previous_data[f'{page_url}_form'] = form_elements_info

            driver.back()
            time.sleep(2)
        except Exception as e:
            print(f"Error handling form for {page_url}: {e}")

with open('changes.json', 'w', encoding='utf-8') as changes_file:
    json.dump(changes, changes_file, indent=4, ensure_ascii=False)

with open('previous_data.json', 'w', encoding='utf-8') as previous_file:
    json.dump(previous_data, previous_file, indent=4, ensure_ascii=False)


def mark_element_on_screenshot(screenshot_path, elements_info, changes):
    image = Image.open(screenshot_path)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    for change_type in ['added', 'modified', 'removed']:
        for xpath, info in changes.get(change_type, {}).items():
            try:
                element = elements_info[xpath]
                location = element['location']
                size = element['size']

                x1, y1 = location['x'], location['y']
                x2, y2 = x1 + size['width'], y1 + size['height']

                screen_width, screen_height = image.size
                page_width = driver.execute_script("return document.body.scrollWidth")
                page_height = driver.execute_script("return document.body.scrollHeight")
                x1 = (x1 / page_width) * screen_width
                y1 = (y1 / page_height) * screen_height
                x2 = (x2 / page_width) * screen_width
                y2 = (y2 / page_height) * screen_height

                draw.rectangle([x1, y1, x2, y2], outline="red", width=2)
                draw.text((x1, y1 - 10), change_type, fill="red", font=font)
            except Exception as e:
                print(f"Error marking element on screenshot: {e}")

    marked_screenshot_path = screenshot_path.replace('screenshots', 'marked_screenshots')
    image.save(marked_screenshot_path)


for page_index, page_url in enumerate(pages.keys(), start=1):
    screenshot_path = f'screenshots/screenshot_{page_index}.png'
    if os.path.exists(screenshot_path):
        mark_element_on_screenshot(screenshot_path, previous_data.get(page_url, {}),
                                   changes.get(page_url, {}).get('changes', {}))

    form_screenshot_path = f'screenshots/form_screenshot_{page_index}_*.png'
    for form_index in range(1, 10):
        form_screenshot_path = f'screenshots/screenshot_{page_index}_{form_index}_form.png'
        if os.path.exists(form_screenshot_path):
            mark_element_on_screenshot(form_screenshot_path, previous_data.get(f'{page_url}_form', {}),
                                       changes.get(f'{page_url}_form', {}).get('form_changes', {}))


def generate_html_report_for_screenshot(screenshot_path, elements_info, changes, page_index):
    html_content = '<html><head><style>'
    html_content += '''
    .highlight {

        position: absolute;
        z-index: 10;

        cursor: pointer;
    }
    .tooltip {
        display: none;
        position: absolute;
        background-color: #f9f9f9;
        border: 1px solid #ccc;
        padding: 10px;
        z-index: 20;
        max-width: 300px;
        word-wrap: break-word;
        background-color: #fff;
        box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
    }
    .tooltip .close-btn {
        float: right;
        font-size: 16px;
        font-weight: bold;
        cursor: pointer;
        color: #aaa;
    }
    '''
    html_content += '</style></head><body>'
    html_content += f'<h2>Screenshot {page_index}</h2>'
    html_content += f'<div style="position: relative; display: inline-block;">'
    html_content += f'<img src="{screenshot_path}" style="width: 100%;"/>'

    for change_type in ['added', 'modified', 'removed']:
        for xpath, info in changes.get(change_type, {}).items():
            element = elements_info.get(xpath, {})
            location = element.get('location', {})
            size = element.get('size', {})
            x1, y1 = location.get('x', 0), location.get('y', 0)
            width, height = size.get('width', 0), size.get('height', 0)
            # Create a unique ID for the tooltip using a combination of page index and XPath
            tooltip_id = f'tooltip_{page_index}_{hash(xpath)}'
            html_content += f'''
            <div class="highlight" style="left: {x1}px; top: {y1 - 10}px; width: {width}px; height: {height}px;"
                 onclick="toggleTooltip('{tooltip_id}')"></div>
            <div id="{tooltip_id}" class="tooltip" style="left: {x1}px; top: {y1 + height + 5}px;">
                <span class="close-btn" onclick="closeTooltip('{tooltip_id}')" style="float:right;">&times;</span>
                <strong>ID:</strong> {element.get('id', 'N/A')}<br>
                <strong>Name:</strong> {element.get('name', 'N/A')}<br>
                <strong>ClassName:</strong> {element.get('className', 'N/A')}<br>
                <strong>XPath:</strong> {xpath}<br>
                <button onclick="copyToClipboard('{element.get('id', '')}')">Copy ID</button>
                <button onclick="copyToClipboard('{element.get('name', '')}')">Copy Name</button>
                <button onclick="copyToClipboard('{element.get('className', '')}')">Copy ClassName</button>
                <button onclick="copyToClipboard('{xpath}')">Copy XPath</button>
            </div>
            '''

    html_content += '</div>'
    html_content += '''
    <script>
    function copyToClipboard(text) {
        var tempInput = document.createElement("textarea");
        document.body.appendChild(tempInput);
        tempInput.value = text;
        tempInput.select();
        document.execCommand("copy");
        document.body.removeChild(tempInput);
    }

    function toggleTooltip(id) {
        var tooltips = document.querySelectorAll('.tooltip');
        tooltips.forEach(function(tip) {
            if (tip.id !== id) {
                tip.style.display = 'none';
            }
        });

        var tooltip = document.getElementById(id);
        if (tooltip.style.display === 'block') {
            tooltip.style.display = 'none';
        } else {
            tooltip.style.display = 'block';
        }
    }

    function closeTooltip(id) {
        var tooltip = document.getElementById(id);
        tooltip.style.display = 'none';
    }
    </script>
    </body></html>
    '''

    report_path = screenshot_path.replace('marked_screenshots', 'reports').replace('.png', '.html')
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    with open(report_path, 'w', encoding='utf-8') as file:
        file.write(html_content)


for page_index, page_url in enumerate(pages.keys(), start=1):
    screenshot_path = f'screenshots/screenshot_{page_index}.png'
    if os.path.exists(screenshot_path):
        mark_element_on_screenshot(screenshot_path, previous_data.get(page_url, {}),
                                   changes.get(page_url, {}).get('changes', {}))
        generate_html_report_for_screenshot(f'marked_screenshots/screenshot_{page_index}.png',
                                            previous_data.get(page_url, {}),
                                            changes.get(page_url, {}).get('changes', {}), page_index)

    form_screenshot_path = f'screenshots/form_screenshot_{page_index}_*.png'
    for form_index in range(1, 10):
        form_screenshot_path = f'screenshots/screenshot_{page_index}_{form_index}_form.png'
        if os.path.exists(form_screenshot_path):
            mark_element_on_screenshot(form_screenshot_path, previous_data.get(f'{page_url}_form', {}),
                                       changes.get(f'{page_url}_form', {}).get('form_changes', {}))
            generate_html_report_for_screenshot(
                f'marked_screenshots/screenshot_{page_index}_{form_index}_form.png',
                previous_data.get(f'{page_url}_form', {}),
                changes.get(f'{page_url}_form', {}).get('form_changes', {}), page_index)

driver.quit()


def move_folder(source_folder, destination_folder):
    try:
        if not os.path.exists(source_folder):
            print(f"Source folder '{source_folder}' does not exist.")
            return

        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)

        shutil.move(source_folder, destination_folder)
        print(f"'{source_folder}' has been moved to '{destination_folder}'.")

    except Exception as e:
        print(f"An error occurred: {e}")


source = '...' #source directory must be add
destination = '...' #destination directory must be add
move_folder(source, destination)

