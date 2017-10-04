from odoo import models, fields, api, _
import datetime
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import UserError, ValidationError
import odoo.addons.decimal_precision as dp


class BookingOrder(models.Model):
    """Booking Order"""
    _name = 'booking.order'
    _rec_name = 'bo_number'
    _description = 'Product Booking Order'

    bo_number = fields.Char(string='Booking Order Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('out', 'out'),
        ('returned', 'Returned'),
        ('sold', 'Sold'),
        ('cancel', 'Calcelled'),
    ], string='Status', readonly=True, copy=False, index=True, default='draft')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True)
    default_start_date = fields.Date('Default Start Date')
    default_end_date = fields.Date('Default End Date')
    booking_order_line = fields.One2many('booking.order.line', 'booking_order_id', string='Order Lines',
                                 states={'out': [('readonly', True)]}, copy=True)
    name = fields.Text('Summary')
    product_id = fields.Many2one('product.product', related='booking_order_line.product_id', string='Product')
    product_serial_number = fields.Char(related='booking_order_line.serial_number', string='Product Serial Number')
    picking_ids = fields.Many2many('stock.picking', compute='_compute_picking_ids',
                                   string='Picking associated to this sale')
    delivery_count = fields.Integer(string='Delivery Orders', compute='_compute_picking_ids')
    invoice_count = fields.Integer(string='# of Invoices', compute='_get_invoiced', readonly=True)
    invoice_ids = fields.Many2many("account.invoice", string='Invoices', compute="_get_invoiced", readonly=True,copy=False)
    products_name = fields.Char('Products Name', compute='_get_products_name')
    delivery_name = fields.Char('Delivery Name', compute='_get_delivery_name')
    invoice_name = fields.Char('Invoice Name', compute='_get_invoice_name')

    @api.multi
    def _get_products_name(self):
        for order in self:
            if order.booking_order_line:
                products = "["
                for line in order.booking_order_line:
                    products += line.product_id.name + ", "
                order.products_name = products + "] "

    @api.multi
    @api.depends('state','booking_order_line')
    def _compute_picking_ids(self):
        for order in self:
            order.picking_ids = self.env['stock.picking'].search(
                [('booking_order_id', '=', order.id)])
            order.delivery_count = len(order.picking_ids)

    @api.multi
    def _get_delivery_name(self):
        for order in self:
            if order.picking_ids:
                delivery = "("
                for picking in order.picking_ids:
                    delivery += picking.name + ", "
                order.delivery_name = delivery + ") "

    @api.multi
    def _get_invoice_name(self):
        for order in self:
            if order.invoice_ids:
                invoice = "("
                for inv in order.invoice_ids:
                    if inv.number: invoice += inv.number + ", "
                if len(invoice) > 2: order.invoice_name = invoice + ")"
                else: order.invoice_name = ""

    @api.multi
    @api.depends('state', 'booking_order_line')
    def _get_invoiced(self):
        inv_obj = self.env['account.invoice']
        for order in self:
            inv_rec = inv_obj.search([('booking_order_id', '=', order.id),('origin','=',order.bo_number)])
            list_inv = inv_rec.ids
            for inv in inv_rec:
                if inv.state != 'draft':
                    if inv.number:
                        inv_ref_rec = inv_obj.search([('origin','=', inv.number)])
                        if inv_ref_rec:
                            list_inv += inv_ref_rec.ids
            order.invoice_ids = [(6, 0, list_inv)]
            order.invoice_count = len(order.invoice_ids)

    @api.model
    def create(self, vals):
        if vals.get('bo_number', _('New')) == _('New'):
            vals['bo_number'] = self.env['ir.sequence'].next_by_code('booking.order') or _('New')
        result = super(BookingOrder, self).create(vals)
        return result

    @api.constrains('default_start_date', 'default_end_date')
    def _check_default_start_end_date(self):
        for rec in self:
            if not rec.default_start_date or not rec.default_end_date:
                raise ValidationError(_('Warning! Default Start and End Date is Required.'))
            else:
                if not datetime.datetime.strptime(rec.default_start_date,
                                                  DEFAULT_SERVER_DATE_FORMAT) <= datetime.datetime.strptime(
                        rec.default_end_date, DEFAULT_SERVER_DATE_FORMAT):
                    raise ValidationError(_('Warning! Default End Date should be greater than or equal to Start Date.'))

    @api.multi
    def action_confirm(self):
        '''This function create Delivery Order for products which is
        in Booking Order'''
        self.ensure_one()
        move_obj = self.env['stock.move']
        for order in self:
            # if len(order.picking_ids) :
            #     order.state = 'out'
            #     return
            picking_rec = self.env['stock.picking'].create({
                'partner_id': self.partner_id.id,
                'picking_type_id': self.env.ref('stock.picking_type_out').id,
                'location_id': self.env.ref('stock.picking_type_out').default_location_src_id.id,
                'origin': self.bo_number,
                'location_dest_id': self.partner_id.property_stock_customer.id,
                'booking_order_id': order.id,
            })
            for line in order.booking_order_line:
                move_obj.create({
                    'name': self.bo_number,
                    'product_id': line.product_id.id,
                    'product_uom': line.product_id.uom_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'location_id': line.product_id.property_stock_inventory.id,
                    'location_dest_id': order.partner_id.property_stock_customer.id,
                    'origin': order.bo_number,
                    'picking_id':picking_rec.id,
                    'date_expected': self.default_start_date,
                })
            order.picking_ids = self.env['stock.picking'].search([('booking_order_id', '=', order.id)])
            order.delivery_count = len(order.picking_ids)
            order.state = 'out'

    @api.multi
    def action_view_delivery(self):
        '''
        This function returns an action that display existing delivery orders
        of given booking order ids. It can either be a in a list or in a form
        view, if there is only one delivery order to show.
        '''
        action = self.env.ref('stock.action_picking_tree_all').read()[0]

        pickings = self.mapped('picking_ids')
        if len(pickings) > 1:
            action['domain'] = [('id', 'in', pickings.ids)]
        elif pickings:
            action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            action['res_id'] = pickings.id
        return action

    @api.multi
    def action_view_invoice(self):
        invoices = self.mapped('invoice_ids')
        action = self.env.ref('account.action_invoice_tree1').read()[0]
        if len(invoices) > 1:
            action['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            action['views'] = [(self.env.ref('account.invoice_form').id, 'form')]
            action['res_id'] = invoices.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    @api.multi
    def sell_products(self):
        view_id = self.env.ref('bipin_20170816_testa.view_sell_booking_products').id
        return {
            'name': _('Sell Product'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'sell.booking.products',
            'views': [(view_id, 'form')],
            'view_id': view_id,
            'target': 'new',
            }

    @api.multi
    def action_return(self):
        for rec in self:
            for rec in self:
                for picking in rec.picking_ids:
                    if picking.state not in ('cancel', 'done') and self.env.ref(
                            'stock.picking_type_out').id == picking.picking_type_id.id:
                        picking.action_cancel()
                    elif picking.state == 'done':
                        move_return = []
                        for move in picking.move_lines:
                            move_return.append((0, 0, {'product_id': move.product_id.id,
                                                       'quantity': move.product_uom_qty,
                                                       'move_id': move.id}))
                        default_data = self.env['stock.return.picking'].with_context(active_ids=picking.ids, active_id=picking.ids[0]) \
                            .default_get([
                            'move_dest_exists',
                            'original_location_id',
                            'parent_location_id',
                            'location_id',
                        ])
                        default_data.update({'product_return_moves': move_return})
                        return_wiz = self.env['stock.return.picking'].with_context(active_ids=picking.ids, active_id=picking.ids[0]) \
                            .create(default_data)
                        return_wiz.create_returns()
                for invoice in rec.invoice_ids:
                    if invoice.state == 'draft':
                        invoice.action_invoice_cancel()
                    elif invoice.state in ('paid', 'open'):
                        default_data = self.env['account.invoice.refund'].with_context(active_ids=invoice.ids, active_id=invoice.ids[0]) \
                            .default_get([
                            'date_invoice',
                            'description',
                            'filter_refund',
                        ])
                        refund_wiz = self.env['account.invoice.refund'].with_context(active_ids=invoice.ids, active_id=invoice.ids[0]) \
                            .create(default_data)
                        refund_wiz.invoice_refund()
                rec.state = 'cancel'
            rec.state = 'returned'

    @api.multi
    def action_sold(self):
        for rec in self:
            for picking in rec.picking_ids:
                if picking.state not in ('cancel', 'done') and self.env.ref(
                        'stock.picking_type_out').id == picking.picking_type_id.id:
                    if picking.state == 'draft':
                        picking.action_confirm()
                        if picking.state != 'assigned':
                            picking.action_assign()
                            if picking.state != 'assigned':
                                raise UserError(_(
                                    "Could not reserve all requested products. Please use the \'Mark as Todo\' button to handle the reservation manually."))
                    for pack in picking.pack_operation_ids:
                        if pack.product_qty > 0:
                            pack.write({'qty_done': pack.product_qty})
                        else:
                            pack.unlink()
                    picking.do_transfer()

            journal_id = self.env['account.invoice'].default_get(['journal_id'])['journal_id']
            if not journal_id:
                raise UserError(_('Please define an accounting sale journal for this company.'))
            if not rec.invoice_ids:
                invoice = self.env['account.invoice'].create({
                    'name': rec.name or '',
                    'origin': rec.bo_number,
                    'type': 'out_invoice',
                    'account_id': rec.partner_id.property_account_receivable_id.id,
                    'partner_id': rec.partner_id.id,
                    'partner_shipping_id': rec.partner_id.id,
                    'journal_id': journal_id,
                    'currency_id': rec.partner_id.property_product_pricelist.currency_id.id,
                    'booking_order_id': rec.id,
                    'comment': rec.name,
                })
                list_inv_line = []
                for booking_line in rec.booking_order_line:
                    account_id = False
                    if booking_line.product_id.id:
                        account_id = booking_line.product_id.property_account_income_id.id
                    if not account_id:
                        raise UserError(_(
                            'There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') %
                                        (booking_line.product_id.name))
                    list_inv_line.append((0, 0, {
                         'origin': rec.bo_number,
                         'name': rec.name or rec.bo_number,
                         'account_id': account_id,
                         'price_unit': booking_line.product_id.lst_price,
                         'quantity': booking_line.product_uom_qty,
                         'uom_id': booking_line.product_id.uom_id.id,
                         'product_id': booking_line.product_id.id}))
                invoice.write({'invoice_line_ids': list_inv_line})

            else:
                invoice = self.env['account.invoice'].create({
                    'name': rec.name or '',
                    'origin': rec.bo_number,
                    'type': 'out_invoice',
                    'account_id': rec.partner_id.property_account_receivable_id.id,
                    'partner_id': rec.partner_id.id,
                    'partner_shipping_id': rec.partner_id.id,
                    'journal_id': journal_id,
                    'currency_id': rec.partner_id.property_product_pricelist.currency_id.id,
                    'booking_order_id': rec.id,
                    'comment': rec.name,
                })
                for inv in rec.invoice_ids:
                    if inv.state  == 'cancel' or inv.origin == rec.bo_number:
                        invoice.invoice_line_ids = inv.invoice_line_ids

            rec.state = 'sold'

    @api.multi
    def action_cancel(self):
        for rec in self:
            for picking in rec.picking_ids:
                if picking.state not in ('cancel', 'done') and self.env.ref(
                        'stock.picking_type_out').id == picking.picking_type_id.id:
                    picking.action_cancel()
                elif picking.state == 'done':
                    move_return = []
                    for move in picking.move_lines:
                        move_return.append((0, 0, {'product_id': move.product_id.id,
                                                   'quantity': move.product_uom_qty,
                                                   'move_id': move.id}))
                    default_data = self.env['stock.return.picking'] \
                        .with_context(active_ids=picking.ids, active_id=picking.ids[0]) \
                        .default_get([
                        'move_dest_exists',
                        'original_location_id',
                        'parent_location_id',
                        'location_id',
                    ])
                    default_data.update({'product_return_moves': move_return})
                    return_wiz = self.env['stock.return.picking'] \
                        .with_context(active_ids=picking.ids, active_id=picking.ids[0]) \
                        .create(default_data)
                    return_wiz.create_returns()
            for invoice in rec.invoice_ids:
                if invoice.state == 'draft':
                    invoice.action_invoice_cancel()
                elif invoice.state in ('paid','open'):
                    default_data = self.env['account.invoice.refund'] \
                        .with_context(active_ids=invoice.ids, active_id=invoice.ids[0]) \
                        .default_get([
                        'date_invoice',
                        'description',
                        'filter_refund',
                    ])
                    refund_wiz = self.env['account.invoice.refund'] \
                        .with_context(active_ids=invoice.ids, active_id=invoice.ids[0]) \
                        .create(default_data)
                    refund_wiz.invoice_refund()
            rec.state = 'cancel'

    @api.multi
    def action_draft(self):
        for rec in self:
            rec.state = 'draft'


class BookingOrderLine(models.Model):
    _name = 'booking.order.line'
    _description = 'Booking Order Line'

    booking_order_id = fields.Many2one('booking.order', string='Booking Order Reference', required=True, index=True, copy=False)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    serial_number = fields.Char('Serial Number', related='product_id.serial_number')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    actual_start_date = fields.Date('Actual Start Date')
    actual_end_date = fields.Date('Actual End Date')
    invoice_lines = fields.Many2many('account.invoice.line', 'booking_order_line_invoice_rel', 'booking_line_id',
                                     'invoice_line_id', string='Invoice Lines', copy=False)
    product_uom_qty = fields.Float('Quantity', required=True, digits=dp.get_precision('Product UoS'), default=1)
    state = fields.Selection([
        ('draft', 'Draft'), ('cancel', 'Cancelled'),
        ('waiting', 'Pending'),
        ('confirmed', 'Waiting Availability'),
        ('partially_available', 'Partially Available'),
        ('assigned', 'Available'), ('done', 'Done')], string='Status', readonly=True, compute='_get_booking_line_state',
        help=" * Draft: not confirmed yet and will not be scheduled until confirmed\n"
             " * Waiting Another Operation: waiting for another move to proceed before it becomes automatically available (e.g. in Make-To-Order flows)\n"
             " * Waiting Availability: still waiting for the availability of products\n"
             " * Partially Available: some products are available and reserved\n"
             " * Ready to Transfer: products reserved, simply waiting for confirmation.\n"
             " * Transferred: has been processed, can't be modified or cancelled anymore\n"
             " * Cancelled: has been cancelled, can't be confirmed anymore")

    @api.multi
    @api.depends('product_id','booking_order_id')
    def _get_booking_line_state(self):
        picking_obj = self.env['stock.picking']
        move_obj = self.env['stock.move']
        for rec in self:
            picking_out_rec = picking_obj.search([('booking_order_id', '=', rec.booking_order_id.id),
                                              ('picking_type_id', '=', self.env.ref('stock.picking_type_out').id)])
            if not picking_out_rec:
                rec.state = 'waiting'
            else:
                flag = True
                for each_out_picking in picking_out_rec:
                    picking_rec_in = picking_obj.search([('picking_type_id', '=', self.env.ref('stock.picking_type_in').id),
                                                     ('origin', '=', each_out_picking.name),
                                                     ('move_lines.product_id','=',rec.product_id.id)])
                    if picking_rec_in:
                        rec.state = picking_rec_in[0].state
                    else:
                        move_done = move_obj.search(
                            [('picking_id', '=', each_out_picking.id), ('product_id', '=', rec.product_id.id)])
                        if move_done:
                            if flag:
                                rec.state = each_out_picking.state
                                flag = False

    @api.multi
    @api.constrains('product_id')
    def _check_product_id(self):
        for rec in self:
            if rec.product_id:
                if not rec.product_id.booking_ok:
                    raise ValidationError(_('Warning! Fllowing field is required in Product for Bookin Order Line\n'
                                        '* Product Serial Number\n*Product Default Preparation Days\n'
                                        '*Product Default Buffer Days'))

    @api.constrains('start_date','end_date')
    def _check_start_end_date(self):
        for rec in self:
            if not rec.start_date or not rec.end_date:
                raise ValidationError(_('Warning! Start and End Date is Required.'))
            else:
                if not datetime.datetime.strptime(rec.start_date, DEFAULT_SERVER_DATE_FORMAT) <= datetime.datetime.strptime(rec.end_date, DEFAULT_SERVER_DATE_FORMAT):
                    raise ValidationError(_('Warning! End Date should be greater than or equal to Start Date.'))

    @api.model
    def create(self, vals):
        if vals.get('product_id', False) and vals.get('start_date', False) and vals.get('end_date', False):
            product_rec = self.env['product.product'].browse(vals.get('product_id'))
            if product_rec.preparation_days and product_rec.buffer_days:
                vals.update({'actual_start_date': datetime.datetime.strptime(vals.get('start_date'),
                                                DEFAULT_SERVER_DATE_FORMAT) - datetime.timedelta(days=product_rec.preparation_days),
                             'actual_end_date': datetime.datetime.strptime(vals.get('end_date'),
                                                DEFAULT_SERVER_DATE_FORMAT) + datetime.timedelta(days=product_rec.buffer_days)})
            else:
                vals.update({'actual_start_date': vals.get('start_date'),
                            'actual_end_date': vals.get('end_date')})
        return super(BookingOrderLine, self).create(vals)

    @api.multi
    def write(self, vals):
        super(BookingOrderLine, self).write(vals)
        if self.product_id and self.product_id.preparation_days and self.product_id.buffer_days:
            if vals.get('start_date', False):
                vals.update({'actual_start_date': datetime.datetime.strptime(vals.get('start_date'),
                                            DEFAULT_SERVER_DATE_FORMAT) - datetime.timedelta(days=self.product_id.preparation_days)})
            elif vals.get('end_date', False):
                vals.update({'actual_end_date': datetime.datetime.strptime(vals.get('end_date'),
                                                DEFAULT_SERVER_DATE_FORMAT) + datetime.timedelta(days=self.product_id.buffer_days)})
        return super(BookingOrderLine, self).write(vals)
