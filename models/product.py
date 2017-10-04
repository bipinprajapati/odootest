from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class product_template(models.Model):
    _inherit = "product.template"

    preparation_days = fields.Integer('Default Preparation Days')
    buffer_days = fields.Integer('Default Buffer Days')
    serial_number = fields.Char('Serial Number')
    booking_ok = fields.Boolean('Can be Booked')

    @api.multi
    def write(self, vals):
        try:
            if vals.get('serial_number', False): int(vals.get('serial_number'))
            return super(product_template, self).write(vals)
        except:
            raise ValidationError(_('Warning! Serial Number must be Integer and Unique.'))

    @api.model
    def create(self, vals):
        try:
            if vals.get('serial_number', False): int(vals.get('serial_number'))
            return super(product_template, self).create(vals)
        except:
            raise ValidationError(_('Warning! Serial Number must be Integer and Unique.'))

    _sql_constraints = [
        ('serial_number', 'unique (serial_number)', 'The Serial Number of the Product must be unique!')]
