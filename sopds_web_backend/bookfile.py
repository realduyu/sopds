# -*- coding: utf-8 -*-

import os
import time
import datetime
import logging
import re

from book_tools.format import create_bookfile
from book_tools.format.util import strip_symbols

from django.db import transaction
from django.utils.translation import ugettext as _

from opds_catalog import fb2parse, opdsdb
from opds_catalog import inpx_parser
import opds_catalog.zipf as zipfile

from constance import config

class bookfile:
    def __init__(self, logger=None):
        self.fb2parser=None
        self.init_parser()

        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger('')
            self.logger.setLevel(logging.CRITICAL)
        self.init_stats()

    def init_stats(self):
        self.t1=datetime.timedelta(seconds=time.time())
        self.t2=self.t1
        self.t3=self.t1
        self.books_added = 0
        self.books_skipped = 0
        self.books_deleted = 0
        self.arch_scanned = 0
        self.arch_skipped = 0
        self.bad_archives = 0
        self.bad_books = 0
        self.books_in_archives = 0

    def init_parser(self):
        self.fb2parser=fb2parse.fb2parser(False)

    def log_options(self):
        self.logger.info(' ***** Starting sopds-scan...')
        self.logger.debug('OPTIONS SET')
        if config.SOPDS_ROOT_LIB!=None:       self.logger.debug('root_lib = %s'%config.SOPDS_ROOT_LIB)
        if config.SOPDS_FB2TOEPUB!=None: self.logger.debug('fb2toepub = %s'%config.SOPDS_FB2TOEPUB)
        if config.SOPDS_FB2TOMOBI!=None: self.logger.debug('fb2tomobi = %s'%config.SOPDS_FB2TOMOBI)
        if config.SOPDS_TEMP_DIR!=None:       self.logger.debug('temp_dir = %s'%config.SOPDS_TEMP_DIR)
        if config.SOPDS_FB2SAX != None:       self.logger.info('FB2SAX = %s'%config.SOPDS_FB2SAX)


    def log_stats(self):
        self.t2=datetime.timedelta(seconds=time.time())
        self.logger.info('Books added      : '+str(self.books_added))
        self.logger.info('Books skipped    : '+str(self.books_skipped))
        self.logger.info('Bad books        : '+str(self.bad_books))
        if config.SOPDS_DELETE_LOGICAL:
            self.logger.info('Books deleted    : '+str(self.books_deleted))
        else:
            self.logger.info('Books DB entries deleted : '+str(self.books_deleted))
        self.logger.info('Books in archives: '+str(self.books_in_archives))
        self.logger.info('Archives scanned : '+str(self.arch_scanned))
        self.logger.info('Archives skipped : '+str(self.arch_skipped))
        self.logger.info('Bad archives     : '+str(self.bad_archives))

        t=self.t2-self.t1
        seconds=t.seconds%60
        minutes=((t.seconds-seconds)//60)%60
        hours=t.seconds//3600
        self.logger.info('Time estimated:'+str(hours)+' hours, '+str(minutes)+' minutes, '+str(seconds)+' seconds.')

    def scan_all(self):
        self.init_stats()
        self.log_options()
        self.inp_cat = None
        self.zip_file = None
        self.rel_path = None     
                    
        opdsdb.avail_check_prepare()
            
        #if config.SOPDS_DELETE_LOGICAL:
        #    self.books_deleted=opdsdb.books_del_logical()
        #else:
        #    self.books_deleted=opdsdb.books_del_phisical()
            
        self.books_deleted=opdsdb.books_del_phisical()
        
        self.log_stats()



    def processfile(self,name,full_path,file,cat,archive=0,file_size=0):
        (n, e) = os.path.splitext(name)
        if e.lower() in config.SOPDS_BOOK_EXTENSIONS.split():
            rel_path=os.path.relpath(full_path,config.SOPDS_ROOT_LIB)
            self.logger.debug("Attempt to add book "+rel_path+"/"+name)
            try:
                if opdsdb.findbook(name, rel_path, 1) == None:
                    if archive==0:
                        cat=opdsdb.addcattree(rel_path,archive)

                    try:
                        book_data = create_bookfile(file, name)
                    except Exception as err:
                        book_data = None
                        self.logger.warning(rel_path + ' - ' + name + ' Book parse error, skipping... (Error: %s)'%err)
                        self.bad_books += 1

                    if book_data:
                        lang = book_data.language_code.strip(strip_symbols) if book_data.language_code else ''
                        title = book_data.title.strip(strip_symbols) if book_data.title else n
                        annotation = book_data.description if book_data.description else ''
                        annotation = annotation.strip(strip_symbols) if isinstance(annotation, str) else annotation.decode('utf8').strip(strip_symbols)
                        docdate = book_data.docdate if book_data.docdate else ''

                        book=opdsdb.addbook(name,rel_path,cat,e[1:],title,annotation,docdate,lang,file_size,archive)
                        self.books_added+=1

                        if archive!=0:
                            self.books_in_archives+=1
                        self.logger.debug("Book "+rel_path+"/"+name+" Added ok.")

                        for a in book_data.authors:
                            author_name = a.get('name',_('Unknown author')).strip(strip_symbols)
                            # Если в имени автора нет запятой, то фамилию переносим из конца в начало
                            if author_name and author_name.find(',')<0:
                                author_names = author_name.split()
                                author_name = ' '.join([author_names[-1],' '.join(author_names[:-1])])
                            author=opdsdb.addauthor(author_name)
                            opdsdb.addbauthor(book,author)

                        for genre in book_data.tags:
                            opdsdb.addbgenre(book,opdsdb.addgenre(genre.lower().strip(strip_symbols)))


                        if book_data.series_info:
                            ser = opdsdb.addseries(book_data.series_info['title'])
                            ser_no = book_data.series_info['index']  or '0'
                            ser_no = int(ser_no) if ser_no.isdigit() else 0
                            opdsdb.addbseries(book,ser,ser_no)
                else:
                    self.books_skipped+=1
                    self.logger.debug("Book "+rel_path+"/"+name+" Already in DB.")
            except UnicodeEncodeError as err:
                self.logger.warning(rel_path + ' - ' + name + ' Book UnicodeEncodeError error, skipping... (Error: %s)' % err)
                self.bad_books += 1

