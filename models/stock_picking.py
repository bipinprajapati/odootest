from odoo import models, fields, api, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    booking_order_id = fields.Many2one('booking.order', string='Booking Order')
