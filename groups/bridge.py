from __future__ import absolute_import, unicode_literals
import sys

from django.shortcuts import render_to_response
from django.conf.urls.defaults import patterns, url as urlpattern
from django.core import urlresolvers
from django.core.urlresolvers import RegexURLPattern, RegexURLResolver

from django.contrib.contenttypes.models import ContentType


class ContentBridge(object):
    
    def __init__(self, group_model, content_app_name=None, urlconf_aware=True):
        self.parent_bridge = None
        self.group_model = group_model
        self.urlconf_aware = urlconf_aware
        
        if content_app_name is None:
            self.content_app_name = group_model._meta.app_label
        else:
            self.content_app_name = content_app_name
        
        # attach the bridge to the model itself. we need to access it when
        # using groupurl to get the correct prefix for URLs for the given
        # group.
        self.group_model.content_bridge = self
    
    def include_urls(self, module_name, url_prefix, kwargs=None):
        if kwargs is None:
            kwargs = {}
        
        prefix = self.content_app_name
        
        __import__(module_name)
        module = sys.modules[module_name]
        
        if hasattr(module, "bridge"):
            module.bridge.parent_bridge = self
        
        urls = []
        
        for url in module.urlpatterns:
            extra_kwargs = {"bridge": self}
            
            if isinstance(url, RegexURLPattern):
                regex = url_prefix + url.regex.pattern.lstrip("^")
                
                if url._callback:
                    callback = url._callback
                else:
                    callback = url._callback_str
                
                if url.name:
                    name = url.name
                else:
                    # @@@ this seems sketchy
                    name = ""
                name = "{0}_{1}".format(prefix, name)
                
                extra_kwargs.update(kwargs)
                extra_kwargs.update(url.default_args)
                
                urls.append(urlpattern(regex, callback, extra_kwargs, name))
            else:
                # i don't see this case happening much at all. this case will be
                # executed likely if url is a RegexURLResolver. nesting an include
                # at the content object level may not be supported, but maybe the
                # code below works. i don't have time to test it, but if you are
                # reading this because something is broken then give it a shot.
                # then report back :-)
                raise Exception("ContentBridge.include_urls does not support a nested include.")
                
                # regex = url_prefix + url.regex.pattern.lstrip("^")
                # urlconf_name = url.urlconf_name
                # extra_kwargs.update(kwargs)
                # extra_kwargs.update(url.default_kwargs)
                # final_urls.append(urlpattern(regex, [urlconf_name], extra_kwargs))
        
        return patterns("", *urls)
    
    @property
    def _url_name_prefix(self):
        if self.urlconf_aware:
            parent_prefix = ""
            if self.parent_bridge is not None:
                parent_prefix = self.parent_bridge._url_name_prefix
            return "{0}{1}_".format(parent_prefix, self.content_app_name)
        else:
            return ""

    def reverse(self, view_name, group, kwargs=None,
                       urlconf=None, prefix=None, current_app=None):
        """Tried to reverse also patterns without group_slug"""
        if kwargs is None:
            kwargs = {}
        final_kwargs = {}
        final_kwargs.update(group.get_url_kwargs())
        final_kwargs.update(kwargs)

        try:
            return_value =  urlresolvers.reverse(
                "{0}{1}".format(self._url_name_prefix, view_name),
                kwargs=final_kwargs,
                urlconf=urlconf,
                prefix=prefix,
                current_app=current_app
            )

        except urlresolvers.NoReverseMatch:
            # group is detected by subdomain or host name
            final_kwargs.pop("{0}_slug".format(
                self.group_model._meta.object_name.lower()
            ))
            return_value =  urlresolvers.reverse(
                "{0}{1}".format(self._url_name_prefix, view_name),
                kwargs=final_kwargs,
                urlconf=urlconf,
                prefix=prefix,
                current_app=current_app
            )

        return return_value
    
    def render(self, template_name, context, context_instance=None):
        # @@@ this method is practically useless -- consider removing it.
        ctype = ContentType.objects.get_for_model(self.group_model)
        return render_to_response([
            "{0}/{1}/{2}".format(ctype.app_label, self.content_app_name, template_name),
            "{0}/{1}".format(self.content_app_name, template_name),
        ], context, context_instance=context_instance)
    
    def group_base_template(self, template_name="content_base.html"):
        return "{0}/{1}".format(self.content_app_name, template_name)
    
    def get_group(self, kwargs):
        
        lookup_params = {}
        
        if self.parent_bridge is not None:
            parent_group = self.parent_bridge.get_group(kwargs)
            lookup_params.update(parent_group.lookup_params(self.group_model))
        else:
            parent_group = None
        
        slug = kwargs.pop("{0}_slug".format(self.group_model._meta.object_name.lower()))
        
        lookup_params.update({
            "slug": slug,
        })
        
        group = self.group_model._default_manager.get(**lookup_params)
        
        if parent_group:
            # cache parent_group on GFK to prevent database hits later on
            group.group = parent_group
        
        return group
        
