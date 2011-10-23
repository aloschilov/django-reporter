from __future__ import with_statement
import os
import sys
import csv
import datetime
from tempfile import NamedTemporaryFile

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.contrib.sites.models import Site
from django.conf import settings
from django.template import Context, loader



REPORTER_FROM_EMAIL = getattr(settings, 'REPORTS_FROM_EMAIL',
                             settings.ADMINS[0][1])

class NotAvailable(Exception):
    pass

class BaseReport(object):
    "A base class for reports to subclass."
    def __init__(self, frequency, date=None, view=False, filename=None,
                 recipients=None, report_args=None):
        if not frequency in self.frequencies:
            raise NotAvailable('The %s frequency is not available for the %s '
                               'report.' % (frequency, self.name))
        self.frequency = frequency
        self.set_dates(date)
        self.view = view
        self.send = True
        if filename or view:
            self.send = False
        self.file = self.get_file(filename)
        self.recipients = None
        if recipients:
            self.recipients = recipients
        self.site = Site.objects.get_current()
        self.args = report_args
    
    def get_file(self, filename):
        """
        Return an appropriate file object.
        """
        if self.view:
            return sys.stdout
        
        if not filename:
            # If the results shouldn't be saved to a file, return a named
            # tempfile
            return NamedTemporaryFile(delete=False)
        if '~' in filename:
            filename = filename.replace('~', os.path.expanduser('~'))
        return open(filename, 'w')
    
    def set_dates(self, date):
        """
        Set the dates to be used in the report. This assigns the following
        attributes to the class:
            tomorrow - 1 day from today or the given date
            one_week - 7 days prior to today or the given date
            one_month - 32 days prior to today or the given date
        """
        if type(date) is datetime.date:
            self.date = date
        else:
            self.date = datetime.date.today()
        self.tomorrow = self.date + datetime.timedelta(days=1)
        self.one_week = self.date - datetime.timedelta(days=7)
        self.one_month = self.date - datetime.timedelta(days=32)
    
    def get_default_recipients(self, recipients):
        """
        Get the default recipients for the report. Should return a list of
        email addresses.
        """
        raise NotImplementedError
    
    def get_data(self):
        "Get the data that is emailed in the report. Should return a string."
        raise NotImplementedError
    
    def get_email_subject(self):
        """
        Get the subject for the email sent with the results. Should return a
        string.
        """
        raise NotImplementedError
    
    def run_report(self):
        "Run the report itself, converting the data into a csv file."

        w = csv.writer(self.file)
        w.writerows(self.get_data())

        self.file.close()

        if self.send:
            self.send_results()

    def send_results(self):
        """
        Send the results to the appropriate email addresses.
        """
        
        if not self.recipients:
            self.recipients = self.get_default_recipients()
        
        template_html = 'reporter/report.html'

        html = loader.get_template(template_html)
        
        data = self.get_data()
        
        subject = self.get_email_subject()
        report_name = self.get_email_subject()
        
        column_headers = data[0]

        d = { 'report_name': report_name,
              'column_headers': column_headers,
              'data': data[1:],
              'column_count': len(column_headers)}
        
        html_content = html.render(Context(d))        
       
        column_max_lens = [max((len(str(data_line[i])) for data_line in data)) for i in xrange(len(data[0]))]
        
        text_content = "+" + "+".join(["-"*current_len for current_len in column_max_lens]) + "+" + "\n\r"
        text_content += "|" + "|".join( (str(data[0][i]) + " "*(column_max_lens[i]-len(str(data[0][i])))) for i in xrange(len(data[0]))) + "|" + "\n\r"
        text_content += "+" + "+".join(["-"*current_len for current_len in column_max_lens]) + "+" + "\n\r"
        
        for data_id in xrange(1,len(data)):
            text_content += "|" + "|".join( (str(data[data_id][i]) + " "*(column_max_lens[i]-len(str(data[data_id][i])))) for i in xrange(len(data[data_id]))) + "|" + "\n\r"

        text_content += "+" + "+".join(["-"*current_len for current_len in column_max_lens]) + "+" + "\n\r"

        msg = EmailMultiAlternatives(subject, text_content, from_email=REPORTER_FROM_EMAIL, to=self.recipients,
                                     attachments=[('%s.%s.csv' % (self.name, self.date),
                                                   open(self.file.name).read(), 'text/plain')])
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        
        os.remove(self.file.name)
        