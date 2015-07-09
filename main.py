import sys,os
abspath = os.path.dirname(__file__)
#raise Exception(abspath)
sys.path.append(abspath)
os.chdir(abspath)

import web
import os
import mime_types
import re
import markdown
import urllib
from datetime import datetime
import time
from mobile.sniffer.detect import  detect_mobile_browser
from mobile.sniffer.utilities import get_user_agent
import json

personal_data = {}
with open("personal.json", "r") as pdata:
  personal_data = json.loads(pdata.read())

urls = (
  '/rescan', 'rescan',
  '/about', 'about',
  '/contact', 'contact',
  '/links', 'links',
  '/static/(.+)', 'static',
  '/comment', 'comment',
  '/entry/(.+)', 'entry',
  '/page/(.+)', 'page',
  '/', 'page',
  '','page')
db = web.database(dbn='mysql', db='blog', user='root', pw=personal_data['dbpass'])
db.printing = False
render = web.template.render('templates/', base = 'layout', globals={'context':web.ctx, 'urllib':urllib, 'markdown':markdown, 'datetime':datetime})
web.config.debug = True

def preprocess(handle):
  "Get a bunch of info regarding the blog context: if the client is mobile, what dates of posts exist, and major tags."
  try:
    web.ctx.daterange=[]
    web.ctx.mobile=False
    web.ctx.tags=personal_data['hottags']
    dates = db.select('blog_entries', what="date", order='date DESC')
    tdr = []
    for date in dates:
      date=date['date']
      conv_date = date.strftime("%Y-%m")
      if not conv_date in tdr:
        tdr.append(conv_date)
        web.ctx.daterange.append(date)
    if detect_mobile_browser(web.ctx.env['HTTP_USER_AGENT']):
      web.ctx.mobile = True
  except Exception as e:
    print e
  return handle()

class about:
  "Page with basic info about blog owner."
  def GET(self):
    try:
      return render.about((datetime.now() - datetime.strptime("1997-08-10","%Y-%m-%d")).days/365)
    except:
      return render.blank("There was a problem processing that request.")

class contact:
  "Page with basic conact info."
  def GET(self):
    try:
      return render.contact()
    except:
      return render.blank("There was a problem processing that request.")

class links:
  "Page with external links"
  def GET(self):
    try:
      return render.links()
    except:
      return render.blank("There was a problem processing that request.")

class page:
  "Gets a page full of post previews."
  def GET(self):
    try:
      params = web.input(page=1,tagged='',start_date='',count=6)
      params.page=int(params.page)
      params.count=int(params.count)
      try:
        params.start_date = datetime.strptime(params.start_date, '%Y-%m-%d')
      except:
        params.start_date = ''
      entries = []
      if params.tagged:
        if params.start_date:
          entries = db.select('blog_entries', where="tags like $tagpattern and date>$start_date", vars={"start_date":params.start_date,"tagpattern":'%'+params.tagged.lower()+'%'}, what="*", limit=params.count, offset=params.count*(params.page-1), order='date ASC')
        else:
          entries = db.select('blog_entries', where="tags like $tagpattern", vars={"tagpattern":'%'+params.tagged.lower()+'%'}, what="*", limit=params.count, offset=params.count*(params.page-1), order='date DESC')
      else:
        if params.start_date:
          entries = db.select('blog_entries', where="date>$start_date", vars={"start_date":params.start_date}, what="*", limit=params.count, offset=params.count*(params.page-1), order='date ASC')
        else:
          entries = db.select('blog_entries', what="*", limit=params.count, offset=params.count*(params.page-1), order='date DESC')
      #if len(entries)<1:
      #  return render.paged([], page_no)
      return render.paged(entries, params.page, params.tagged, params.start_date)
    except:
      return render.blank("There was a problem processing that request.")

class comment:
  def GET(self, p=0):
    return self.POST()
  def POST(self):
    "Add a comment to the database."
    try:
      params = web.input(post_id=None,name='Anonymous',email='',make_email_public=False,contents='')
      db.insert('comments', post_id=params.post_id, name=params.name, email=params.email, make_email_public=(1 if params.make_email_public else 0), date=time.strftime("%Y-%m-%d %H:%M:%S"), contents=params.contents)
      raise web.seeother('/entry/'+params.post_id)
    except Exception as e:
      print e
      return render.blank("There was a problem processing that request.")


scan_location = personal_data['scandir']
class static:
  "Unpreferred method... this simulates a static directory."
  def GET(self, filename):
    try:
      filename = re.sub('\.\./|\./|~|<|>|:|"|\|?|', '', scan_location+'static/'+filename).replace('//','/').rstrip('/')
      if os.path.isdir(filename):
        return ""
      else:
        try:
          web.header('Content-Type',mime_types.types[filename.split('/')[-1].split('.')[-1]][1])
        except:
          web.header('Content-Type','unknown')
        web.header('Content-disposition', 'attachment; filename=' + filename.split('/')[-1])
          

        with open(filename) as f:
          rval = f.read()
        return rval
    except:
      pass

class entry:
  "Gets a specific, detailed, full post."
  def GET(self, entry_id):
    try:
      variables = {"id":entry_id}
      matches = db.select("blog_entries", where="id=$id", vars=variables)
      if len(matches)<1:
        return render.blank("Entry not found.")
      post = matches[0]
      comments = db.select("comments", where="post_id=$id", vars=variables, what="*", order="date DESC")
      return render.entry(
        post['title'],
        entry_id,
        post['date'],
        filter(None,post['tags'].split(',')),
        markdown.markdown(post["start_content"])+"<br/>"+markdown.markdown(post["end_content"]) if post["format"].lower() == "markdown" else post["start_content"]+"<br/>"+post["end_content"],
        comments )
    except:
      return render.blank("Entry not found.")

class rescan:
  "Scans scan_location for posts and stores them in database."
  def GET(self):
    try:
      # List paths in the scan folder
      paths = os.listdir(scan_location)
      good_paths = []
      for path in paths:
        try:
          # Only look at HTML files
          if not path.endswith('.html'):
            continue
          filename = path[:-5]
          good_paths.append(filename)

          start_content = ""
          end_content = ""
          date = None
          title = ""
          tags = ""
          format = ""
          # Open up the file
          with open(scan_location+path) as blog_entry:
            in_header = True
            in_start = True
            # Parse headers, body before READMORE, and body after READMORE block.
            for line in blog_entry:
              try:
                line = line.strip('\r\n')
                if line and in_header:
                  directive = line.strip().split(' ', 1)
                  if directive[0].lower() == "title:":
                    title = directive[1]
                  elif directive[0].lower() == "tags:":
                    tags = ','+ ','.join([tag.strip() for tag in directive[1].lower().split(',')])+','
                  elif directive[0].lower() == "format:":
                    format = directive[1].lower()
                  elif directive[0].lower() == "date:":
                    date = directive[1].lower()

                else:
                  in_header = False
                  if line == 'READMORE':
                    in_start = False
                  elif in_start:
                    start_content+=line+'\n'
                  else:
                    end_content+=line+'\n'

              except: pass

          # if there is a blog entry already, update it.
          if len(db.select('blog_entries', where='id=$id', vars={"id":filename}, what="*")):
            db.update('blog_entries', where="id=$id", vars={"id":filename}, start_content=start_content, end_content=end_content, title=title, tags=tags, date=date, format=format)
          # Otherwise, make one!
          else:
            db.insert('blog_entries', id=filename, start_content=start_content, end_content=end_content, title=title, tags=tags, date=date, format=format)
        except: pass
      # Delete every blog entry we didn't see in the scanning process.
      db.delete('blog_entries', where="id not in $good_paths", vars={"good_paths":good_paths})
    except Exception as e:
      return e
    raise web.seeother('/')

app = web.application(urls, globals())
app.add_processor(preprocess)
application = app.wsgifunc()
