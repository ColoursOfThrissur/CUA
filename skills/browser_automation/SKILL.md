# Browser Automation Skill

## Overview
Advanced browser automation, web scraping, and interactive web tasks using headless or visible browser instances.

## Capabilities
- **Web Element Interaction**: Click buttons, fill forms, navigate pages
- **Data Extraction**: Scrape structured data from web pages
- **Screenshot Capture**: Take screenshots of pages or specific elements
- **Form Automation**: Fill and submit web forms automatically
- **Page Navigation**: Navigate through multi-page workflows

## Preferred Tools
- **BrowserAutomationTool**: Primary tool for all browser automation tasks

## Verification Mode
- **side_effect_observed**: Requires evidence of browser actions (screenshots, scraped data, form submissions)

## Risk Level
- **High**: Browser automation can interact with external websites and modify web state

## Output Types
- **automation_result**: Results of browser automation tasks
- **screenshot**: Image captures of web pages
- **scraped_data**: Extracted data from web pages
- **interaction_result**: Results of web element interactions

## Use Cases
1. **Web Scraping**: Extract data from websites that require JavaScript execution
2. **Form Automation**: Fill out and submit web forms automatically
3. **UI Testing**: Automated testing of web applications
4. **Screenshot Generation**: Capture visual representations of web pages
5. **Multi-step Workflows**: Navigate through complex web processes

## Fallback Strategy
Falls back to web_research skill for simpler web content retrieval tasks.