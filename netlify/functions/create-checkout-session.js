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
  bpc157:      { name: 'BPC-157',      price: 8900  },
  tb500:       { name: 'TB-500',       price: 10900 },
  ghkcu:       { name: 'GHK-CU',       price: 7500  },
  gt1500:      { name: 'GT1500',       price: 9500  },
  cjc1295:     { name: 'CJC-1295',     price: 8900  },
  ipamorelin:  { name: 'Ipamorelin',   price: 9900  },
  retatrutide: { name: 'Retatrutide',  price: 12900 },
  bb10:        { name: 'BB10',         price: 15900 },
  mt2:         { name: 'MT2',          price: 7900  },
  klow80:      { name: 'KLOW80',       price: 21900 },
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
  for (const item of cart) {
    const product = PRODUCTS[item.id];
    if (!product) {
      return { statusCode: 400, body: JSON.stringify({ error: `Unknown product: ${item.id}` }) };
    }
    const quantity = Math.max(1, Math.min(99, parseInt(item.quantity, 10) || 1));
    line_items.push({
      price_data: {
        currency: 'aud',
        product_data: { name: product.name },
        unit_amount: product.price,
      },
      quantity,
    });
  }

  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      line_items,
      success_url: `${SITE_URL}/?checkout=success`,
      cancel_url: `${SITE_URL}/?checkout=cancelled`,
      shipping_address_collection: { allowed_countries: ['AU'] },
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
