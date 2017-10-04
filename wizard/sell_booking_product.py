from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SellBookingProducts(models.TransientModel):
    _name = "sell.booking.products"

    @api.multi
    def _get_booking_id(self):
        return self.env.context.get('active_ids', [])[0]

    booking_line_ids = fields.Many2many('booking.order.line',
                                   string='Picking associated to this sale')
    booking_order_id = fields.Many2one('booking.order', string='Booking Order',
                                       default=_get_booking_id)

    @api.multi
    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        self.ensure_one()
        journal_id = self.env['account.invoice'].default_get(['journal_id'])['journal_id']
        if not journal_id:
            raise UserError(_('Please define an accounting sale journal for this company.'))
        invoice_vals = {
            'name': self.booking_order_id.name or '',
            'origin': self.booking_order_id.bo_number,
            'type': 'out_invoice',
            'account_id': self.booking_order_id.partner_id.property_account_receivable_id.id,
            'partner_id': self.booking_order_id.partner_id.id,
            'partner_shipping_id': self.booking_order_id.partner_id.id,
            'journal_id': journal_id,
            'currency_id': self.booking_order_id.partner_id.property_product_pricelist.currency_id.id,
            'booking_order_id': self.booking_order_id.id,
            'comment': self.booking_order_id.name,
        }
        return invoice_vals

    @api.multi
    def _process_delivery_order(self):
        """Done all Delivery Order after creating the Invoice
        for selected products. For other products Delivery order
        will be in draft state.
        """
        flag = False
        for rec in self:
            list_product = []
            move_obj = self.env['stock.move']
            for booking_line in rec.booking_line_ids:
                list_product.append(booking_line.product_id.id)
            for each_picking in rec.booking_order_id.picking_ids:
                if each_picking.state not in ('cancel', 'done') and self.env.ref('stock.picking_type_out').id == each_picking.picking_type_id.id:
                    move_done = move_obj.search([('picking_id','=',each_picking.id),('product_id','in',list_product)])
                    move_remmaining = move_obj.search([('picking_id','=',each_picking.id),('product_id','not in',list_product)])
                    each_picking.move_lines = [(6, 0, move_done.ids)]
                    if each_picking.state == 'draft':
                        each_picking.action_confirm()
                        if each_picking.state != 'assigned':
                            each_picking.action_assign()
                            if each_picking.state != 'assigned':
                                raise UserError(_(
                                    "Could not reserve all requested products. Please use the \'Mark as Todo\' button to handle the reservation manually."))
                    for pack in each_picking.pack_operation_ids:
                        if pack.product_qty > 0:
                            pack.write({'qty_done': pack.product_qty})
                        else:
                            pack.unlink()
                    each_picking.do_transfer()
                    if move_remmaining:
                        picking_rec = self.env['stock.picking'].create({
                            'partner_id': rec.booking_order_id.partner_id.id,
                            'picking_type_id': self.env.ref('stock.picking_type_out').id,
                            'location_id': self.env.ref('stock.picking_type_out').default_location_src_id.id,
                            'origin': rec.booking_order_id.bo_number,
                            'location_dest_id': rec.booking_order_id.partner_id.property_stock_customer.id,
                            'booking_order_id': rec.booking_order_id.id
                        })
                        picking_rec.move_lines = [(6, 0, move_remmaining.ids)]
                    flag = True
            picking_rec = self.env['stock.picking'].search(
                [('booking_order_id', '=', rec.booking_order_id.id), ('state', 'in', ['done', 'cancel'])])
            if len(rec.booking_order_id.picking_ids) == len(picking_rec) and len(rec.booking_order_id.picking_ids) != 0:
                rec.booking_order_id.state = 'out'
            return flag

    @api.multi
    def no_invoice(self):
        '''Cancel Delivery orders if not in DONE or CANCEL state and if Delivery Order
        if DONE state then it will RETURN for selected products.
        Also cancel those Invoices which is in DRAFT state, IF Invoive is not in DRAFT state
         then it will REFUND to customer for Selected Products'''
        for rec in self:
            if not rec.booking_line_ids:
                raise ValidationError(
                    _('Warning! Select some products to process!'))
            list_product = []
            move_obj = self.env['stock.move']
            picking_obj = self.env['stock.picking']
            inv_obj = self.env['account.invoice']
            inv_line_obj = self.env['account.invoice.line']
            product_obj = self.env['product.product']
            for booking_line in rec.booking_line_ids:
                list_product.append(booking_line.product_id.id)
            for each_picking in rec.booking_order_id.picking_ids:
                if each_picking.state not in ('cancel', 'done') and self.env.ref(
                        'stock.picking_type_out').id == each_picking.picking_type_id.id:
                    move_done = move_obj.search(
                        [('picking_id', '=', each_picking.id), ('product_id', 'in', list_product)])
                    move_remmaining = move_obj.search(
                        [('picking_id', '=', each_picking.id), ('product_id', 'not in', list_product)])
                    each_picking.move_lines = [(6, 0, move_done.ids)]
                    each_picking.action_cancel()
                    if move_remmaining:
                        picking_rec = self.env['stock.picking'].create({
                            'partner_id': rec.booking_order_id.partner_id.id,
                            'picking_type_id': self.env.ref('stock.picking_type_out').id,
                            'location_id': self.env.ref('stock.picking_type_out').default_location_src_id.id,
                            'origin': rec.booking_order_id.bo_number,
                            'location_dest_id': rec.booking_order_id.partner_id.property_stock_customer.id,
                            'booking_order_id': rec.booking_order_id.id
                        })
                        picking_rec.move_lines = [(6, 0, move_remmaining.ids)]
                elif each_picking.state == 'done' and self.env.ref(
                        'stock.picking_type_out').id == each_picking.picking_type_id.id:
                    move_done = move_obj.search(
                        [('picking_id', '=', each_picking.id), ('product_id', 'in', list_product)])

                    picking_rec_in = picking_obj.search([('picking_type_id', '=', self.env.ref('stock.picking_type_in').id),
                                                         ('origin','=',each_picking.name)])
                    for picking_rec in picking_rec_in:
                        move_in = move_obj.search(
                            [('picking_id', '=', picking_rec.id), ('product_id', 'in', list_product)])
                        for move_exist in move_in:
                            invoice_rec = self.env['account.invoice'].search(
                                [('booking_order_id', '=', rec.booking_order_id.id),
                                 ('invoice_line_ids.product_id', 'in', list_product),
                                 ('state','!=','cancel')])
                            if not invoice_rec:
                                raise ValidationError(
                                    _('Warning! Return Delivery for %s product is already created!') % (
                                        move_exist.product_id.name))
                    if move_done:
                        move_return = []
                        for move in move_done:
                            move_return.append((0, 0, {'product_id': move.product_id.id,
                                                       'quantity': move.product_uom_qty,
                                                       'move_id': move.id}))
                        default_data = self.env['stock.return.picking'] \
                            .with_context(active_ids=each_picking.ids, active_id=each_picking.ids[0]) \
                            .default_get([
                            'move_dest_exists',
                            'original_location_id',
                            'parent_location_id',
                            'location_id',
                        ])
                        default_data.update({'product_return_moves':move_return})
                        return_wiz = self.env['stock.return.picking'] \
                            .with_context(active_ids=each_picking.ids, active_id=each_picking.ids[0]) \
                            .create(default_data)
                        return_wiz.create_returns()

            invoice_rec = self.env['account.invoice'].search([('booking_order_id','=',rec.booking_order_id.id),
                                                              ('invoice_line_ids.product_id','in',list_product)])

            i = 0
            for each_invoice in invoice_rec:
                if i == len(rec.booking_line_ids.ids):
                    break
                i += 1
                if each_invoice.state == 'draft':
                    each_invoice.action_invoice_cancel()
                elif each_invoice.state in ('paid','open'):
                    default_data = self.env['account.invoice.refund'] \
                        .with_context(active_ids=each_invoice.ids, active_id=each_invoice.ids[0]) \
                        .default_get([
                        'date_invoice',
                        'description',
                        'filter_refund',
                    ])
                    refund_wiz = self.env['account.invoice.refund'] \
                        .with_context(active_ids=each_invoice.ids, active_id=each_invoice.ids[0]) \
                        .create(default_data)
                    refund_wiz.invoice_refund()


                if len(each_invoice.invoice_line_ids) != len(list_product):
                    inv_pro_list = []
                    inv_line_list = []
                    for line in each_invoice.invoice_line_ids:
                        inv_pro_list.append(line.product_id.id)
                        inv_line_list.append(line)
                    flag = 0
                    for k in list_product:
                        if k in inv_pro_list:
                            inv_pro_list.remove(k)
                            inv_line_list.pop(flag)
                        flag += 1
                    if len(inv_pro_list) > 0:

                        invoice_vals = rec._prepare_invoice()
                        invoice = inv_obj.create(invoice_vals)
                        inc_pro = 0
                        for product in inv_pro_list:
                            product_id = product_obj.browse(product)
                            account_id = False
                            if product_id.id:
                                account_id = product_id.property_account_income_id.id
                            if not account_id:
                                raise UserError(_(
                                    'There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') %
                                        (product_id.name))
                            inv_line_obj.create({'invoice_id': invoice.id,
                                                 'origin': rec.booking_order_id.bo_number,
                                                 'name': rec.booking_order_id.name or rec.booking_order_id.bo_number,
                                                 'account_id': account_id,
                                                 'price_unit': product_id.lst_price,
                                                 'quantity': inv_line_list[inc_pro].quantity,
                                                 'uom_id': product_id.uom_id.id,
                                                 'product_id': product_id.id})
                            inc_pro += 1




    @api.multi
    def invoice_create(self):
        '''Create Invoice for selected products and process the Delivery Order
        for the same'''
        inv_obj = self.env['account.invoice']
        inv_line_obj = self.env['account.invoice.line']
        for rec in self:
            if not rec.booking_line_ids:
                raise ValidationError(_('Warning! Select product to process!'))
            if rec.booking_line_ids:
                list_inv_line = []
                inv_rec = inv_obj.search([('booking_order_id', '=', self.booking_order_id.id)])
                # if inv_rec:
                for inv in inv_rec:
                    for booking_line in rec.booking_line_ids:
                        for inv_line in inv.invoice_line_ids:
                            if booking_line.product_id.id != inv_line.product_id.id:
                                list_inv_line.append(booking_line.id)
                            elif booking_line.product_id.id == inv_line.product_id.id:
                                # and len(inv.invoice_line_ids.ids) > 1
                                book_pro_list = []
                                for pro in rec.booking_order_id.booking_order_line:
                                    book_pro_list.append(pro.product_id.id)

                                if inv.state != 'cancel' and book_pro_list.count(booking_line.product_id.id) == 1:
                                    raise ValidationError(_('Warning! Invoice for %s product is already exist against this Booking Order!') % (booking_line.product_id.name))
                                else:
                                    list_inv_line.append(booking_line.id)
                    rec.booking_line_ids = [(6, 0, list_inv_line)]
                invoice_vals = rec._prepare_invoice()
                invoice = inv_obj.create(invoice_vals)
                for line in rec.booking_line_ids:
                    account_id = False
                    if line.product_id.id:
                        account_id = line.product_id.property_account_income_id.id
                    if not account_id:
                        raise UserError(_('There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') %
                            (line.product_id.name))
                    inv_line_obj.create({'invoice_id': invoice.id,
                         'origin': rec.booking_order_id.bo_number,
                         'name': rec.booking_order_id.name or rec.booking_order_id.bo_number,
                         'account_id': account_id,
                         'price_unit': line.product_id.lst_price,
                         'quantity': line.product_uom_qty,
                         'uom_id': line.product_id.uom_id.id,
                         'product_id': line.product_id.id})
            res = rec._process_delivery_order()
            if not res:
                move_obj = self.env['stock.move']
                picking_rec = self.env['stock.picking'].create({
                    'partner_id': rec.booking_order_id.partner_id.id,
                    'picking_type_id': self.env.ref('stock.picking_type_out').id,
                    'location_id': self.env.ref('stock.picking_type_out').default_location_src_id.id,
                    'origin': rec.booking_order_id.bo_number,
                    'location_dest_id': rec.booking_order_id.partner_id.property_stock_customer.id,
                    'booking_order_id': rec.booking_order_id.id
                })
                for line in rec.booking_line_ids:
                    move_obj.create({
                        'name': rec.booking_order_id.bo_number,
                        'product_id': line.product_id.id,
                        'product_uom': line.product_id.uom_id.id,
                        'product_uom_qty': line.product_uom_qty,
                        'location_id': line.product_id.property_stock_inventory.id,
                        'location_dest_id': rec.booking_order_id.partner_id.property_stock_customer.id,
                        'origin': rec.booking_order_id.bo_number,
                        'picking_id': picking_rec.id,
                        'date_expected': rec.booking_order_id.default_start_date,
                    })

