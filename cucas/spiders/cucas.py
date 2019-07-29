# -*- coding: utf-8 -*-
import scrapy
from selenium import webdriver

from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from w3lib.html import remove_tags


class CucasSpider(scrapy.Spider):
    name = 'cucas'
    allowed_domains = ['cucas.edu.cn']
    start_urls = ['https://www.cucas.edu.cn/school_redirect/schoollist']
    custom_settings = {'FEED_FORMAT': 'json', 'FEED_URI': 'data/cucas_%(time)s.json'}

    browser = webdriver.Firefox()
    browser.set_window_size(1600, 1200)


    def parse(self, response):
        # find the list of all universities
        univ_urls = [u for u in response.css('.xxSeaList a::attr(href)').getall()
                     if 'reviews' not in u]

        self.logger.info(f'Found {len(univ_urls)} universities')

        for univ_url in univ_urls:
            yield scrapy.Request(univ_url, self.parse_univ_main)


    def parse_univ_main(self, response):

        # we are on a university main page
        # data to be scraped: name, level, type and location

        info_box = response.css('.l_t_left p a::text').getall()
        admission = response.css('.tags li a::attr(href)').get().strip()

        university = {
            'name': response.css('.l_mid a::text').get(),
            'level': info_box[1],
            'type': info_box[2],
            'location': ", ".join(info_box[3:]),
            'programs': []
        }
        return scrapy.Request(response.urljoin(admission), self.parse_admission, meta={'university': university})


    def parse_admission(self, response):
        """
        On admission page there are three level programs bachelor, master and doctoral,
        each in its own tab, needs clicking to follow
        """

        meta = response.request.meta

        levels = (
                    ("select_course(2)", 'undergraduate_data'),
                    ("select_course(3)", 'master_data'),
                    ("select_course(4)", 'doctor_data')
                  )

        program_urls = []

        for level in levels:
            level_urls = self.click_on_level(response.request.url, *level)
            if level_urls:
                program_urls.extend(level_urls)

        if program_urls:
            first_program_url = program_urls.pop(0)
            meta.update({'program_urls': program_urls})
            yield scrapy.Request(
                first_program_url, self.parse_program,
                meta=meta)


    def click_on_level(self, admission_url, onclick, data_title):
        """
        Click on a certain program level to retrieve urls for each program detail.
        Deals with the javascript onclick on site

        :param onclick: the number for program (defined by the site)
        :param data_title: tag id for the table data
        :return: list of urls to scrape
        """
        try:

            self.browser.get(admission_url)
            level_tab = WebDriverWait(self.browser, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, f'.c_tab li[onclick="{onclick}"] a')))
            # first move to the element
            self.browser.execute_script("return arguments[0].scrollIntoView(true);", level_tab)
            # then scroll by x, y values, in this case 10 pixels up
            self.browser.execute_script("window.scrollBy(0, -100);")
            level_tab.click()

            programs = WebDriverWait(self.browser, 30).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, f'#{data_title} tr td:first-child a')))

            return [p.get_attribute('href') for p in programs]
        except Exception as e:
            self.logger.exception(f'Execption during getting programs refs: {e}')
            return None


    def parse_program(self, response):
        self.logger.info(f"getting program info from: {response.request.url}")

        try:
            next_program_urls = response.request.meta['program_urls']

            program = {}

            program['name'] = response.css('.title h3::text').get().strip()
            program['level'] = response.css('.title em::text').get().strip()
            date_duration_table = response.css('.hidden-sm .zhai table:nth-child(2)')
            program['starting_date'] = (
                date_duration_table.css('tr:first-child td:nth-child(2)::text')
                    .get()
                    .replace('&nbsp', ' ')
            )
            program['duration'] = (
                date_duration_table.css('tr:nth-child(2) td:nth-child(2)::text')
                    .get()
                    .replace('&nbsp', ' ')
            )

            descr_table = response.css('.right .zhai table:nth-of-type(2)')
            program['teaching_language'] = descr_table.css('tr:nth-child(1) td:nth-child(2)::text').get().strip()
            program['deadline'] = (
                descr_table.css('tr:nth-child(2) td:nth-child(2)::text')
                    .get()
                    .replace('&nbsp', ' ')
            )
            program['tuition'] = descr_table.css('tr:nth-child(3) td:nth-child(2)::text').get()
            program['application_fee'] = descr_table.css('tr:nth-child(4) td:nth-child(2)::text').get()

            program['description'] = parse_large_text_section(response.css('.m_2+div'))
            program['entry_requirements'] = parse_large_text_section(response.css('.m_7+div'))

            program['fees'] = parse_large_text_section(response.css('.m_3+div'))
            program['application_material'] = parse_large_text_section(response.css('.m_4+div'))

            university = response.request.meta['university']
            university['programs'].append(program)

            # stack programs into the university while there are some
            if next_program_urls:
                next_program_url = next_program_urls.pop(0)
                yield scrapy.Request(
                    next_program_url, self.parse_program,
                    meta={'university': university, 'program_urls': next_program_urls})
            else:
                yield university

        except:
            self.logger.error("ERROR getting program info: ", exc_info=True)



def parse_large_text_section(selector):
    if not selector:
        return None
    result = []
    children = selector.css('div > *')
    for child in children:
        tag_name = child.xpath('name()').get()
        if tag_name == 'table':
            result.append({'content': child.get()})
        elif tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            result.append({'heading': child.css('::text').get()})
        elif tag_name == 'div':
            parse_large_text_section(child)
        else:
            child_text = child.get()
            if child_text:
                child_text = remove_tags(child_text)
            if not child_text:
                continue
            result.append({'content': child_text})
    return result
