# -*- coding: utf-8 -*-
{
    'name': 'Product Booking',
    'version': '1.0',
    'website': 'https://www.google.com',
    'category': 'Marketing',
    'summary': 'Manage the Product Booking Orders',
    'depends': ['website','sale','purchase','stock','calendar','website_sale','website_crm'],
    'data': [
        'views/product_view.xml',
        'views/booking_order_view.xml',
        'views/templates.xml',
        'wizard/sell_booking_products_view.xml',
        'data/ir_sequence_data.xml',
        'data/data.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'auto_install': False,
}
