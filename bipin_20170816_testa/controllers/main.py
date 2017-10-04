import json
import logging
from werkzeug.exceptions import Forbidden

from odoo import http, tools, _
from odoo.http import request
from odoo.addons.base.ir.ir_qweb.fields import nl2br
from odoo.addons.website.models.website import slug
from odoo.addons.website.controllers.main import QueryURL
from odoo.exceptions import ValidationError
from odoo.addons.website_form.controllers.main import WebsiteForm


class web_form(WebsiteForm):

    @http.route(auth="public", website=True)
    def website_form(self, model_name, **kwargs):
        website_form = super(web_form, self).website_form(model_name,**kwargs)
        print "OOOOOOOOOO>>>>>>>>>>>>>",website_form
        print "OOOOOOOOOO>>>>model_name>>>>>>>>>", model_name
        print "-------**kwargs------------", kwargs
        cc = request.env['res.users'].sudo().create({'name': kwargs.get('partner_name'),
                                             'login': kwargs.get('email_from')})
        print "ccccccccccccccccccccc", cc
        return website_form



class WebsiteSaleForm(http.Controller):

    @http.route(['/my/products',], type='http', auth="public", website=True)
    def my_products(self, page=0, category=None, search='', ppg=False, **post):
        print '>>>>>>>>>>>>>> call...'
        rec_par = request.env['res.partner'].sudo().search([])

        values = {'partners': rec_par}
        return request.render("bipin_20170816_testa.myproducts", values)


    @http.route(['/partner/<id>',], type='http', auth="public", website=True)
    def partner_data(self,id, **post):
        print '>>>>>>>>>>>>>> call...',id
        rec_par = request.env['res.partner'].sudo().search([('id','=',id)])

        values = {'partners': rec_par}
        return request.render("bipin_20170816_testa.myproducts", values)

    @http.route(['/page/signup', ], type='http', auth="public", website=True)
    def sign_up(self, page=0, category=None, search='', ppg=False, **post):
        print '>>>>>>>>>>>>>> call...'
        return request.render("bipin_20170816_testa.signuppage1")
