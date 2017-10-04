from odoo import api, fields, models, _


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    booking_order_id = fields.Many2one('booking.order', string='Booking Order')