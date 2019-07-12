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
        universities = response.css('.xxSeaList a::attr(href)').getall()
        universities = [u for u in universities if 'reviews' not in u]

        for university in universities:
            yield scrapy.Request(university, self.parse_univ_main)

    def parse_univ_main(self, response):
        # once on a university: name, level, type and location
        attr = response.css('.l_t_left p a::text').getall()
        admission = response.css('.tags li a::attr(href)').get().strip()

        university = {
            'name': response.css('.l_mid a::text').get(),
            'level': attr[1],
            'type': attr[2],
            'location': ", ".join(attr[3:])
        }
        yield scrapy.Request(response.urljoin(admission), self.parse_admission, meta={'university': university})

    def click_on_program(self, onclick, data_title):
        try:
            bachelor_tab = self.browser.find_element_by_css_selector(f'.c_tab li[onclick="{onclick}"] a')
            bachelor_tab.click()
            time.sleep(2)
            programs = self.browser.find_elements_by_css_selector(f'#{data_title} tr td:first-child a')
            program_urls = []
            for p in programs:
                program_urls.append(p.get_attribute('href'))
            return program_urls
        except:
            return None

    def parse_admission(self, response):
        """
        once on admission there are three level programs bachelor, master and doctoral
        """
        self.browser.get(response.request.url)

        university = response.request.meta['university']

        # bachelor
        bachelors = self.click_on_program("select_course(2)", 'undergraduate_data')
        if bachelors:
            for url in bachelors:
                yield scrapy.Request(url, self.parse_program, meta={'university': university})

        # master
        masters = self.click_on_program("select_course(3)", 'master_data')
        if masters:
            for url in masters:
                yield scrapy.Request(url, self.parse_program, meta={'university': university})

        # doctor
        doctors = self.click_on_program("select_course(4)", 'doctor_data')
        for url in doctors:
            yield scrapy.Request(url, self.parse_program, meta={'university': university})


    def parse_program(self, response):
        self.logger.info("getting program info: ")

        try:
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
            university['program'] = program

            yield university

        except:
            self.logger.error("ERROR getting program info: ", exc_info=True)
