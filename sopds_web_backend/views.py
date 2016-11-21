from random import randint

from django.shortcuts import render, redirect
from django.template.context_processors import csrf
from django.db.models import Count, Min
from django.utils.translation import ugettext as _
from django.contrib.auth import authenticate, login, REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.core.urlresolvers import reverse, reverse_lazy

from opds_catalog import models
from opds_catalog.models import Book, Author, Series, bookshelf, Counter, Catalog, Genre
from opds_catalog.settings import MAXITEMS, DOUBLES_HIDE, AUTH, VERSION, ALPHABET_MENU, SPLITITEMS, FB2TOEPUB, FB2TOMOBI
from opds_catalog.models import lang_menu
from opds_catalog.opds_paginator import Paginator as OPDS_Paginator

from sopds_web_backend.settings import HALF_PAGES_LINKS

def sopds_login(function=None, redirect_field_name=REDIRECT_FIELD_NAME, url=None):
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated(),
        login_url=reverse_lazy(url),
        redirect_field_name=redirect_field_name
    )
    if function:
        return actual_decorator(function) if AUTH else function
    return actual_decorator

def sopds_processor(request):
    args={}
    args['sopds_auth']=AUTH
    args['sopds_version']=VERSION
    args['alphabet'] = ALPHABET_MENU
    args['splititems'] = SPLITITEMS
    args['fb2tomobi'] = (FB2TOMOBI!="")
    args['fb2toepub'] = (FB2TOEPUB!="")
    if ALPHABET_MENU:
        args['lang_menu'] = lang_menu
    
    user=request.user
    if user.is_authenticated():
        result=[]
        for row in bookshelf.objects.filter(user=user).order_by('-readtime')[:8]:
            book = Book.objects.get(id=row.book_id)
            p = {'id':row.id, 'readtime': row.readtime, 'book_id': row.book_id, 'title': book.title, 'authors':book.authors.values()}       
            result.append(p)    
        args['bookshelf']=result
        
    books_count = Counter.objects.get_counter(models.counter_allbooks)
    if books_count:
        random_id = randint(1,books_count)
        try:
            random_book = Book.objects.all()[random_id-1:random_id][0]
        except Book.DoesNotExist:
            random_book= None
    else:
        random_book= None        
                   
    args['random_book'] = random_book
    stats = { d['name']:d['value'] for d in Counter.obj.all().values() }
    stats['lastscan_date']=Counter.obj.get(name='allbooks').update_time
    args['stats'] = stats
  
    return args

# Create your views here.
@sopds_login(url='web:login')
def SearchBooksView(request):
    #Read searchtype, searchterms, searchterms0, page from form
    args = {}
    args.update(csrf(request))

    if request.GET:
        searchtype = request.GET.get('searchtype', 'm')
        searchterms = request.GET.get('searchterms', '')
        #searchterms0 = int(request.POST.get('searchterms0', ''))
        page_num = int(request.GET.get('page', '1'))
        page_num = page_num if page_num>0 else 1
        
        #if (len(searchterms)<3) and (searchtype in ('m', 'b', 'e')):
        #    args['errormsg'] = 'Too few symbols in search string !';
        #    return render_to_response('sopds_error.html', args)
        
        if searchtype == 'm':
            #books = Book.objects.extra(where=["upper(title) like %s"], params=["%%%s%%"%searchterms.upper()]).order_by('title','-docdate')
            books = Book.objects.filter(search_title__contains=searchterms.upper()).order_by('search_title','-docdate')
            args['breadcrumbs'] = [_('Books'),_('Search by title'),searchterms]
            args['searchobject'] = 'title'
            
        if searchtype == 'b':
            #books = Book.objects.extra(where=["upper(title) like %s"], params=["%s%%"%searchterms.upper()]).order_by('title','-docdate')
            books = Book.objects.filter(search_title__startswith=searchterms.upper()).order_by('search_title','-docdate')
            args['breadcrumbs'] = [_('Books'),_('Search by title'),searchterms]   
            args['searchobject'] = 'title'         
            
        elif searchtype == 'a':
            try:
                author_id = int(searchterms)
                author = Author.objects.get(id=author_id)
                #aname = "%s %s"%(author.last_name,author.first_name)
                aname = author.full_name
            except:
                author_id = 0
                aname = ""                  
            books = Book.objects.filter(authors=author_id).order_by('search_title','-docdate')  
            args['breadcrumbs'] = [_('Books'),_('Search by author'),aname]   
            args['searchobject'] = 'author' 
            
        # Поиск книг по серии
        elif searchtype == 's':
            try:
                ser_id = int(searchterms)
                ser = Series.objects.get(id=ser_id).ser
            except:
                ser_id = 0
                ser = ""
            books = Book.objects.filter(series=ser_id).order_by('search_title','-docdate')    
            args['breadcrumbs'] = [_('Books'),_('Search by series'),ser]
            args['searchobject'] = 'series'
            
        # Поиск книг по жанру
        elif searchtype == 'g':
            try:
                genre_id = int(searchterms)
                section = Genre.objects.get(id=genre_id).section
                subsection = Genre.objects.get(id=genre_id).subsection
                args['breadcrumbs'] = [_('Books'),_('Search by genre'),section,subsection]
            except:
                genre_id = 0
                args['breadcrumbs'] = [_('Books'),_('Search by genre')]
                
            books = Book.objects.filter(genres=genre_id).order_by('search_title','-docdate') 
            args['searchobject'] = 'genre'
                                   
        # Поиск книг на книжной полке            
        elif searchtype == 'u':
            if AUTH:
                books = Book.objects.filter(bookshelf__user=request.user).order_by('-bookshelf__readtime')
                args['breadcrumbs'] = [_('Books'),_('Bookshelf'),request.user.username]
                #books = bookshelf.objects.filter(user=request.user).select_related('book')              
            else:
                books={}        
                args['breadcrumbs'] = [_('Books'), _('Bookshelf')] 
            args['searchobject'] = 'title'
            args['isbookshelf'] = 1
                
        # Поиск дубликатов для книги            
        elif searchtype == 'd':
            #try:
            book_id = int(searchterms)
            mbook = Book.objects.get(id=book_id)
            books = Book.objects.filter(title__iexact=mbook.title, authors__in=mbook.authors.all()).exclude(id=book_id).distinct().order_by('-docdate')
            args['breadcrumbs'] = [_('Books'),_('Doubles for book'),mbook.title]
            args['searchobject'] = 'title'
            
        elif searchtype == 'i':
            try:
                book_id = int(searchterms)
                mbook = Book.objects.get(id=book_id)
            except:
                book_id = 0
                mbook = None
            #books = Book.objects.filter(id=book_id) 
            books = Book.objects.filter(title__iexact=mbook.title, authors__in=mbook.authors.all()).distinct().order_by('-docdate')                
            args['breadcrumbs'] = [_('Books'),mbook.title]
            args['searchobject'] = 'title'
        
        # prefetch_related on sqlite on items >999 therow error "too many SQL variables"    
        #if len(books)>0:
        #    books = books.select_related('authors','genres','series')
        
        # Фильтруем дубликаты и формируем выдачу затребованной страницы
        books_count = books.count()
        op = OPDS_Paginator(books_count, 0, page_num, MAXITEMS, HALF_PAGES_LINKS)
        items = []
        
        prev_title = ''
        prev_authors_set = set()
        
        # Начаинам анализ с последнего элемента на предидущей странице, чторбы он "вытянул" с этой страницы
        # свои дубликаты если они есть
        summary_DOUBLES_HIDE =  DOUBLES_HIDE and (searchtype != 'd')
        start = op.d1_first_pos if ((op.d1_first_pos==0) or (not summary_DOUBLES_HIDE)) else op.d1_first_pos-1
        finish = op.d1_last_pos
        
        for row in books[start:finish]:
            p = {'doubles':0, 'lang_code': row.lang_code, 'filename': row.filename, 'path': row.path, \
                  'registerdate': row.registerdate, 'id': row.id, 'annotation': row.annotation, \
                  'docdate': row.docdate, 'format': row.format, 'title': row.title, 'filesize': row.filesize//1000,
                  'authors':row.authors.values(), 'genres':row.genres.values(), 'series':row.series.values()}       
            if summary_DOUBLES_HIDE:
                title = p['title'] 
                authors_set = {a['id'] for a in p['authors']}         
                if title==prev_title and authors_set==prev_authors_set:
                    items[-1]['doubles']+=1
                else:
                    items.append(p)                   
                prev_title = title
                prev_authors_set = authors_set
            else:
                items.append(p)
                
        # "вытягиваем" дубликаты книг со следующей страницы и удаляем первый элемент который с предыдущей страницы и "вытягивал" дубликаты с текущей
        if summary_DOUBLES_HIDE:
            double_flag = True
            while (finish<books_count) and double_flag:
                finish += 1  
                if books[finish].title==prev_title and {a['id'] for a in books[finish].authors.values()}==prev_authors_set:
                    items[-1]['doubles']+=1
                else:
                    double_flag = False   
            
            if op.d1_first_pos!=0:     
                items.pop(0)                                   
              
        args['paginator'] = op.get_data_dict()
        args['searchterms']=searchterms;
        args['searchtype']=searchtype;
        args['books']=items   
        args['current'] = 'search'  
        
    return render(request,'sopds_books.html', args)

@sopds_login(url='web:login')
def SearchSeriesView(request):
    #Read searchtype, searchterms, searchterms0, page from form
    args = {}
    args.update(csrf(request))

    if request.GET:
        searchtype = request.GET.get('searchtype', 'm')
        searchterms = request.GET.get('searchterms', '')
        #searchterms0 = int(request.POST.get('searchterms0', ''))
        page_num = int(request.GET.get('page', '1'))
        
        if searchtype == 'm':
            series = Series.objects.filter(search_ser__contains=searchterms.upper())
        elif searchtype == 'b': 
            series = Series.objects.filter(search_ser__startswith=searchterms.upper())
        elif searchtype == 'e':
            series = Series.objects.filter(search_ser=searchterms.upper())      

        #if len(series)>0:
        #    series = series.order_by('ser')   
        series = series.annotate(count_book=Count('book')).distinct().order_by('search_ser') 
            
        # Создаем результирующее множество
        series_count = series.count()
        op = OPDS_Paginator(series_count, 0, page_num, MAXITEMS, HALF_PAGES_LINKS)        
        items = []
        for row in series:
            #p = {'id':row.id, 'ser':row.ser, 'lang_code': row.lang_code, 'book_count': Book.objects.filter(series=row).count()}
            p = {'id':row.id, 'ser':row.ser, 'lang_code': row.lang_code, 'book_count': row.count_book}
            items.append(p)                     
              
        args['paginator'] = op.get_data_dict()
        args['searchterms']=searchterms;
        args['searchtype']=searchtype;
        args['series']=items     
        args['searchobject'] = 'series'
        args['current'] = 'search'        
        args['breadcrumbs'] = [_('Series'),_('Search'),searchterms]
                                              
    return render(request,'sopds_series.html', args)

@sopds_login(url='web:login')
def SearchAuthorsView(request):
    #Read searchtype, searchterms, searchterms0, page from form    
    args = {}
    args.update(csrf(request))

    if request.GET:
        searchtype = request.GET.get('searchtype', 'm')
        searchterms = request.GET.get('searchterms', '')
        #searchterms0 = int(request.POST.get('searchterms0', ''))
        page_num = int(request.GET.get('page', '1'))
        
        if searchtype == 'm':
            authors = Author.objects.filter(search_full_name__contains=searchterms.upper()).order_by('search_full_name')   
        elif searchtype == 'b':
            authors = Author.objects.filter(search_full_name__startswith=searchterms.upper()).order_by('search_full_name')    
        elif searchtype == 'e': 
            authors = Author.objects.filter(search_full_name=searchterms.upper()).order_by('search_full_name')    
                        
        # Создаем результирующее множество
        authors_count = authors.count()
        op = OPDS_Paginator(authors_count, 0, page_num, MAXITEMS, HALF_PAGES_LINKS)        
        items = []
        
        for row in authors:
            p = {'id':row.id, 'full_name':row.full_name, 'lang_code': row.lang_code, 'book_count': Book.objects.filter(authors=row).count()}
            items.append(p)                     
            
        args['paginator'] = op.get_data_dict()              
        args['searchterms']=searchterms;
        args['searchtype']=searchtype;
        args['authors']=items     
        args['searchobject'] = 'author'
        args['current'] = 'search'       
        args['breadcrumbs'] = [_('Authors'),_('Search'),searchterms]
                                    
    return render(request,'sopds_authors.html', args)

@sopds_login(url='web:login')
def CatalogsView(request):   
    args = {}

    if request.GET:
        cat_id = request.GET.get('cat', None)
        page_num = int(request.GET.get('page', '1'))   
    else:
        cat_id = None
        page_num = 1

    try:
        if cat_id is not None:
            cat = Catalog.objects.get(id=cat_id)
        else:
            cat = Catalog.objects.get(parent__id=cat_id)
    except Catalog.DoesNotExist:
        cat = None
    
    catalogs_list = Catalog.objects.filter(parent=cat).order_by("cat_name")
    catalogs_count = catalogs_list.count()
    # prefetch_related on sqlite on items >999 therow error "too many SQL variables"
    #books_list = Book.objects.filter(catalog=cat).prefetch_related('authors','genres','series').order_by("title")
    books_list = Book.objects.filter(catalog=cat).order_by("search_title")
    books_count = books_list.count()
    
    # Получаем результирующий список
    op = OPDS_Paginator(catalogs_count, books_count, page_num, MAXITEMS, HALF_PAGES_LINKS)
    items = []
    
    for row in catalogs_list[op.d1_first_pos:op.d1_last_pos]:
        p = {'is_catalog':1, 'title': row.cat_name,'id': row.id, 'cat_type':row.cat_type, 'parent_id':row.parent_id}       
        items.append(p)
          
    for row in books_list[op.d2_first_pos:op.d2_last_pos]:
        p = {'is_catalog':0, 'lang_code': row.lang_code, 'filename': row.filename, 'path': row.path, \
              'registerdate': row.registerdate, 'id': row.id, 'annotation': row.annotation, \
              'docdate': row.docdate, 'format': row.format, 'title': row.title, 'filesize': row.filesize//1000,
              'authors':row.authors.values(), 'genres':row.genres.values(), 'series':row.series.values()}         
        items.append(p)
                    
    args['paginator'] = op.get_data_dict()
    args['items']=items
    args['cat_id'] = cat_id
    args['current'] = 'catalog'     
    
    breadcrumbs_list = []
    if cat:
        while (cat.parent):
            breadcrumbs_list.insert(0, (cat.cat_name, cat.id))
            cat = cat.parent
        breadcrumbs_list.insert(0, (_('ROOT'), 0))  
    breadcrumbs_list.insert(0, (_('Catalogs'),-1))    
    args['breadcrumbs_cat'] =  breadcrumbs_list  
      
    return render(request,'sopds_catalogs.html', args)  

@sopds_login(url='web:login')
def BooksView(request):   
    args = {}

    if request.GET:
        lang_code = int(request.GET.get('lang', '0'))  
        chars = request.GET.get('chars', '')
    else:
        lang_code = 0
        chars = ''
        
    length = len(chars)+1
    if lang_code:
        sql="""select %(length)s as l, substring(search_title,1,%(length)s) as id, count(*) as cnt 
               from opds_catalog_book 
               where lang_code=%(lang_code)s and search_title like '%(chars)s%%%%'
               group by substring(search_title,1,%(length)s) 
               order by id"""%{'length':length, 'lang_code':lang_code, 'chars':chars}
    else:
        sql="""select %(length)s as l, substring(search_title,1,%(length)s) as id, count(*) as cnt 
               from opds_catalog_book 
               where search_title like '%(chars)s%%%%'
               group by substring(search_title,1,%(length)s) 
               order by id"""%{'length':length,'chars':chars}
      
    items = Book.objects.raw(sql)
          
    args['items']=items
    args['current'] = 'book'      
    args['lang_code'] = lang_code   
    args['breadcrumbs'] =  [_('Books'),_('Select'),lang_menu[lang_code],chars]
      
    return render(request,'sopds_selectbook.html', args)      

@sopds_login(url='web:login')
def AuthorsView(request):   
    args = {}

    if request.GET:
        lang_code = int(request.GET.get('lang', '0'))  
        chars = request.GET.get('chars', '')
    else:
        lang_code = 0
        chars = ''
        
    length = len(chars)+1
    if lang_code:
        sql="""select %(length)s as l, substring(search_full_name,1,%(length)s) as id, count(*) as cnt 
               from opds_catalog_author 
               where lang_code=%(lang_code)s and search_full_name like '%(chars)s%%%%'
               group by substring(search_full_name,1,%(length)s) 
               order by id"""%{'length':length, 'lang_code':lang_code, 'chars':chars}
    else:
        sql="""select %(length)s as l, substring(search_full_name,1,%(length)s) as id, count(*) as cnt 
               from opds_catalog_author 
               where search_full_name like '%(chars)s%%%%'
               group by substring(search_full_name,1,%(length)s) 
               order by id"""%{'length':length,'chars':chars}
      
    items = Author.objects.raw(sql)
          
    args['items']=items
    args['current'] = 'author'      
    args['lang_code'] = lang_code   
    args['breadcrumbs'] =  [_('Authors'),_('Select'),lang_menu[lang_code],chars]
      
    return render(request,'sopds_selectauthor.html', args)    

@sopds_login(url='web:login')
def SeriesView(request):   
    args = {}

    if request.GET:
        lang_code = int(request.GET.get('lang', '0'))  
        chars = request.GET.get('chars', '')
    else:
        lang_code = 0
        chars = ''
        
    length = len(chars)+1
    if lang_code:
        sql="""select %(length)s as l, substring(search_ser,1,%(length)s) as id, count(*) as cnt 
               from opds_catalog_series 
               where lang_code=%(lang_code)s and search_ser like '%(chars)s%%%%'
               group by substring(search_ser,1,%(length)s)
               order by id"""%{'length':length, 'lang_code':lang_code, 'chars':chars}
    else:
        sql="""select %(length)s as l, substring(search_ser,1,%(length)s) as id, count(*) as cnt 
               from opds_catalog_series 
               where search_ser like '%(chars)s%%%%'
               group by substring(search_ser,1,%(length)s) 
               order by id"""%{'length':length,'chars':chars}
      
    items = Series.objects.raw(sql)
          
    args['items']=items
    args['current'] = 'series'      
    args['lang_code'] = lang_code   
    args['breadcrumbs'] =  [_('Series'),_('Select'),lang_menu[lang_code],chars]
      
    return render(request,'sopds_selectseries.html', args)

@sopds_login(url='web:login')
def GenresView(request):   
    args = {}

    if request.GET:
        section_id = int(request.GET.get('section', '0'))  
    else:
        section_id = 0
        
    if section_id==0:
        items = Genre.objects.values('section').annotate(section_id=Min('id'), num_book=Count('book')).filter(num_book__gt=0).order_by('section')
        args['breadcrumbs'] =  [_('Genres'),_('Select')]
    else:
        section = Genre.objects.get(id=section_id).section
        items = Genre.objects.filter(section=section).annotate(num_book=Count('book')).filter(num_book__gt=0).values().order_by('subsection')   
        args['breadcrumbs'] =  [_('Genres'),_('Select'),section]   
          
    args['items']=items
    args['current'] = 'genre'  
    args['parent_id'] = section_id     
       
    return render(request,'sopds_selectgenres.html', args)

@sopds_login(url='web:login')
def BSDelView(request):
    if request.GET:
        book = request.GET.get('book', None)
    else:
        book = None
       
    book = int(book)
       
    bookshelf.objects.filter(user=request.user, book=book).delete()
    
    return redirect("%s?searchtype=u"%reverse("web:searchbooks"))
    
def hello(request):
    args = {}
    args['breadcrumbs'] = [_('HOME')]
    return render(request, 'sopds_hello.html', args)

def LoginView(request):
    args = {}
    args['breadcrumbs'] = [_('Login')]
    args.update(csrf(request))
    try:
        username = request.POST['username']
        password = request.POST['password']
    except KeyError:
        return render(request, 'sopds_login.html', args) 
    
    next_url = request.GET.get('next',reverse("web:main"))

    user = authenticate(username=username, password=password)
    if user is not None:
        if user.is_active:
            login(request, user)
            return redirect(next_url)
        else:
            args['system_message']={'text':_('This account is not active!'),'type':'alert'}
            return render(request, 'sopds_login.html', args)
    else:
        args['system_message']={'text':_('User does not exist or the password is incorrect!'),'type':'alert'}
        return render(request, 'sopds_login.html', args)
    
    return render(request, 'sopds_login.html', args)

def LogoutView(request):
    args = {}
    args['breadcrumbs'] = [_('Logout')]
    return redirect(reverse('web:main'))
