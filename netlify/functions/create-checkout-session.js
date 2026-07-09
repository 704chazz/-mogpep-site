// netlify/functions/create-checkout-session.js
//
// Creates a real Stripe Checkout Session for a multi-item cart.
// Prices are looked up here, server-side, from PRODUCTS below —
// never trusted from the client — so someone editing the page's
// JS in devtools can't check out with a fake price.

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

const SITE_URL = process.env.SITE_URL || 'https://mogpep.com';

// Source of truth for prices/names. Keep this in sync with the
// product data in index.html. Prices are in cents.
const PRODUCTS = {
  bpc157:      { name: 'BPC-157',      price: 5999  },
  tb500:       { name: 'TB-500',       price: 5999  },
  ghkcu:       { name: 'GHK-CU',       price: 8999  },
  gt1500:      { name: 'GT1500',       price: 7999  },
  cjc1295:     { name: 'CJC-1295',     price: 8999  },
  ipamorelin:  { name: 'Ipamorelin',   price: 8999  },
  retatrutide: { name: 'Retatrutide',  price: 11999 },
  bb10:        { name: 'BB10',         price: 10999 },
  mt2:         { name: 'MT2',          price: 5999  },
  klow80:      { name: 'KLOW80',       price: 15999 },
  motsc:       { name: 'MOTS-c',       price: 5999  },
  tesamorelin: { name: 'Tesamorelin',  price: 8999  },
  semax:       { name: 'Semax',        price: 7999  },
};

exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  if (!process.env.STRIPE_SECRET_KEY) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'STRIPE_SECRET_KEY is not configured on the server.' }),
    };
  }

  let cart;
  try {
    cart = JSON.parse(event.body).items;
  } catch (e) {
    return { statusCode: 400, body: JSON.stringify({ error: 'Invalid request body.' }) };
  }

  if (!Array.isArray(cart) || cart.length === 0) {
    return { statusCode: 400, body: JSON.stringify({ error: 'Cart is empty.' }) };
  }

  const line_items = [];
  let totalQty = 0;
  for (const item of cart) {
    const product = PRODUCTS[item.id];
    if (!product) {
      return { statusCode: 400, body: JSON.stringify({ error: `Unknown product: ${item.id}` }) };
    }
    const quantity = Math.max(1, Math.min(99, parseInt(item.quantity, 10) || 1));
    totalQty += quantity;
    line_items.push({
      price_data: {
        currency: 'aud',
        product_data: { name: product.name },
        unit_amount: product.price,
      },
      quantity,
    });
  }

  // Site policy: 2+ vials ships free express; a single vial pays a flat
  // express fee. We only offer express shipping — no standard option.
  const isFreeShipping = totalQty >= 2;
  const shipping_options = [{
    shipping_rate_data: {
      type: 'fixed_amount',
      fixed_amount: { amount: isFreeShipping ? 0 : 1500, currency: 'aud' },
      display_name: isFreeShipping ? 'Free Express Shipping' : 'Express Shipping',
      delivery_estimate: {
        minimum: { unit: 'business_day', value: 1 },
        maximum: { unit: 'business_day', value: 3 },
      },
    },
  }];

  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      line_items,
      success_url: `${SITE_URL}/?checkout=success`,
      cancel_url: `${SITE_URL}/?checkout=cancelled`,
      shipping_address_collection: { allowed_countries: ['AU'] },
      shipping_options,
      allow_promotion_codes: true,
    });

    return {
      statusCode: 200,
      body: JSON.stringify({ url: session.url }),
    };
  } catch (err) {
    console.error('Stripe error:', err);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Could not create checkout session.' }),
    };
  }
};
