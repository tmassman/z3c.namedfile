# -*- coding: utf-8 -*-

# python imports
try:
    from os import SEEK_END
except ImportError:
    from posixfile import SEEK_END
import urllib

# zope imports
from z3c.form.browser import file
from z3c.form.interfaces import IDataManager, IFieldWidget, IFormLayer, NOVALUE
from z3c.form.widget import FieldWidget
from zope.component import adapter, getMultiAdapter
from zope.interface import implementer, implements, implementsOnly
from zope.publisher.browser import BrowserView, FileUpload
from zope.publisher.interfaces import IPublishTraverse, NotFound
from zope.security.proxy import removeSecurityProxy
from zope.security._proxy import _Proxy as Proxy
from zope.traversing.browser import absoluteURL

# local imports
from z3c.namedfile.browser.interfaces import INamedFileWidget, INamedImageWidget
from z3c.namedfile.file import NamedFile
from z3c.namedfile.interfaces import INamed, INamedFileField, INamedImage, INamedImageField
from z3c.namedfile.utils import safe_basename, set_headers, stream_data


class NamedFileWidget(file.FileWidget):
    """A widget for a named file object."""
    implementsOnly(INamedFileWidget)

    klass = u'named-file-widget'
    value = None # don't default to a string

    @property
    def allow_nochange(self):
        return not self.ignoreContext and \
            self.field is not None and \
            self.value is not None and \
            self.value != self.field.missing_value

    @property
    def filename(self):
        if self.field is not None and self.value == self.field.missing_value:
            return None
        elif INamed.providedBy(self.value):
            return self.value.filename
        elif isinstance(self.value, FileUpload):
            return safe_basename(self.value.filename)
        else:
            return None

    @property
    def file_size(self):
        if INamed.providedBy(self.value):
            return self.value.getSize() / 1024
        else:
            return 0

    @property
    def filename_encoded(self):
        filename = self.filename
        if filename is None:
            return None
        else:
            if isinstance(filename, unicode):
                filename = filename.encode('utf-8')
            return urllib.quote_plus(filename)

    @property
    def download_url(self):
        if self.field is None:
            return None
        if self.ignoreContext:
            return None
        if self.filename_encoded:
            return "%s/++widget++%s/@@download/%s" % (self.request.getURL(),
                self.field.__name__, self.filename_encoded)
        else:
            return "%s/++widget++%s/@@download" % (self.request.getURL(),
                self.field.__name__)

    def action(self):
        action = self.request.get("%s.action" % self.name, "nochange")
        if hasattr(self.form, 'successMessage') and self.form.status == \
            self.form.successMessage:
            # if form action completed successfully, we want nochange
            action = 'nochange'
        return action

    def extract(self, default=NOVALUE):
        action = self.request.get("%s.action" % self.name, None)
        if self.request.get('PATH_INFO', '').endswith('kss_z3cform_inline_validation'):
            action = 'nochange'

        if action == 'remove':
            return None
        elif action == 'nochange':
            if self.ignoreContext:
                return default
            dm = getMultiAdapter((self.context, self.field), IDataManager)
            value = dm.query()
            # TODO: Do we realy have to remove the security proxy?
            if isinstance(value, Proxy):
                value = removeSecurityProxy(value)
            return value

        # empty unnamed FileUploads should not count as a value
        value = super(NamedFileWidget, self).extract(default)
        if isinstance(value, FileUpload):
            value.seek(0, SEEK_END)
            empty = value.tell() == 0
            value.seek(0)
            if empty and not value.filename:
                return default
            value.seek(0)
        return value

    def absolute_url(self):
        return absoluteURL(self.context, self.request)


class NamedImageWidget(NamedFileWidget):
    """A widget for a named image object."""
    implementsOnly(INamedImageWidget)

    klass = u'named-image-widget'

    @property
    def width(self):
        if INamedImage.providedBy(self.value):
            return self.value.getImageSize()[0]
        else:
            return None

    @property
    def height(self):
        if INamedImage.providedBy(self.value):
            return self.value.getImageSize()[1]
        else:
            return None

    @property
    def thumb_width(self):
        width = self.width
        if not width:
            return 128
        else:
            return min(width, 128)

    @property
    def thumb_height(self):
        height = self.height
        if not height:
            return 128
        else:
            return min(height, 128)

    @property
    def alt(self):
        return self.title


class Download(BrowserView):
    implements(IPublishTraverse)

    def __init__(self, context, request):
        context = removeSecurityProxy(context)
        super(Download, self).__init__(context, request)
        self.filename = None

    def publishTraverse(self, request, name):
        if self.filename is None: # ../@@download/filename
            self.filename = name
        else:
            raise NotFound(self, name, request)
        return self

    def __call__(self):
        if self.context.ignoreContext:
            raise NotFound("Cannot get the data file from a widget with no context")

        context = self.context.context
        field = self.context.field
        dm = getMultiAdapter((context, field,), IDataManager)
        file_ = dm.query()
        if file_ is None:
            raise NotFound(self, self.filename, self.request)
        if not self.filename:
            self.filename = getattr(file_, 'filename', None)
        set_headers(file_, self.request.response, filename=self.filename)
        return stream_data(file_)


@implementer(IFieldWidget)
@adapter(INamedFileField, IFormLayer)
def NamedFileFieldWidget(field, request):
    return FieldWidget(field, NamedFileWidget(request))


@implementer(IFieldWidget)
@adapter(INamedImageField, IFormLayer)
def NamedImageFieldWidget(field, request):
    return FieldWidget(field, NamedImageWidget(request))
