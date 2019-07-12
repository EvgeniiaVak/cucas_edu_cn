# -*- coding: utf-8 -*-
import scrapy
from selenium import webdriver
import time


class CucasSpider(scrapy.Spider):
    name = 'cucas'
    allowed_domains = ['cucas.edu.cn']
    start_urls = ['https://www.cucas.edu.cn/school_redirect/schoollist']
    custom_settings = {'FEED_FORMAT': 'json', 'FEED_URI': 'data/cucas_%(time)s.json'}

    browser = webdriver.Firefox()


    def parse(self, response):
        # find the list of all universities
        univ_urls = [u for u in response.css('.xxSeaList a::attr(href)').getall()
                     if 'reviews' not in u]

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

        levels = (("select_course(2)", 'undergraduate_data'),
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
            level_tab = self.browser.find_element_by_css_selector(f'.c_tab li[onclick="{onclick}"] a')
            level_tab.click()
            time.sleep(2)

            programs = self.browser.find_elements_by_css_selector(f'#{data_title} tr td:first-child a')

            return [p.get_attribute('href') for p in programs]
        except:
            return None


    def parse_program(self, response):
        self.logger.info("getting program info: ")

        try:
            next_program_urls = response.request.meta['program_urls']

            program = {}

            """
            if inside the program for each: name, starting date, deadline, duration, and tuition.
            """

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

            """        
            then on drop down menu you get program
    
             - description,
             - entry requirement,
             - fee structure,
             - application material
            """

            description = response.css('.m_2+div *::text').getall()
            if description:
                program['description'] = "\n".join(description)

            requirements = response.css('.m_7+div *::text').getall()
            requirements = [r.strip() for r in requirements]
            requirements = [r for r in requirements if r]
            program['entry_requirements'] = requirements

            program['fees'] = "\n".join(response.css('.m_3+div table *::text').getall())
            program['application_material'] = "\n".join(response.css('.m_4+div *::text').getall())

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
