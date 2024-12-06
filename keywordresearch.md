

I want to create a keyword research tool that leverages DataforSEO API.  I have a couple of tools already coded and need to build a UI around them.
/home/vikas/Code/seoclientmanager/apps/agents/tools/keyword_tools/keyword_tools.py
/home/vikas/Code/seoclientmanager/apps/agents/tools/keyword_tools/ranked_keywords_tool.py

the views should be in /home/vikas/Code/seoclientmanager/apps/seo_manager/views/keyword_views.py

The UI should match the rest of the application using SoftUI Dashboard PRO widgets in /templates/pages/widgets.html

API calls for clients should be processed and stored in the db models /home/vikas/Code/seoclientmanager/apps/seo_manager/models.py

The architecture should be model heavy, views light.

I also want to add a caching layer to the API calls using djangocache.  the tools will need to be modified to use the cache layer. the cache for dataforseo calls should expire after 7 days.

Logging is done using import logging

You are an expert in Django, Bootstrap5. Use this starter that was build by AppSeed [Soft Dashboard PRO Django](https://appseed.us/product/soft-ui-dashboard-pro/django/).  Leverage it's prebuilt components and styling.

Bootstrap 5 - Open source front end framework
noUISlider - JavaScript Range Slider
Popper.js - Kickass library used to manage poppers 
Flatpickr - Useful library used to select date
Choices JS - A nice plugin that select elements with intuitive multiselection and searching but also for managing tags.
CountUp JS - A dependency-free, lightweight JavaScript class that can be used to quickly create animations that display numerical data in a more interesting way.
Charts Js - Simple yet flexible JavaScript charting for designers & developers
FullCalendar - Full-sized drag & drop event calendar
Dropzone - An open source library that provides drag’n’drop file uploads with image previews.
Datatables - DataTables but in Vanilla ES2018 JS
jKanban - Pure agnostic Javascript plugin for Kanban boards
PhotoSwipe - JavaScript image gallery for mobile and desktop, modular, framework independent
Quill - A free, open source WYSIWYG editor built for the modern web
Sweet Alerts - A beautiful, responsive, customisable, accessible replacement for Javascript’s popup boxes.
three.js - JavaScript 3D library
Wizard - Animated Multi-step form for Bootstrap
propose using the above libraries when relevant to a ui component

template tag for loading js files is {% block extra_js %}
template tag for extra styles is {% block extra_css %}