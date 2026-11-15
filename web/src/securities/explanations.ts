// What each figure on a security's page means and how to read it: to learn to judge a company, not only see numbers.
// Plain language, a few sentences each; general guidance, not advice about any one company.

export const EXPLANATIONS = {
  pe:
    "Price to earnings: what investors pay for each dollar of yearly profit per share. 33 means the price is 33 times last year's earnings. " +
    "A high P/E usually means the market expects strong growth (or is optimistic); a low one, slow growth or doubts. Compare it with the " +
    "company's own history (the bar below) and with similar companies, not across sectors. Not meaningful when the company loses money.",
  marketCap:
    "Market capitalisation: what all the company's shares are worth together at today's price, the market's price tag for the whole company. " +
    "Large caps (hundreds of billions) are usually steadier; small caps can grow faster but swing more.",
  sharesOutstanding:
    "How many shares exist. Your share of the company is your shares divided by this. A count that rises over the years dilutes owners " +
    "(each share owns less); a falling one (buybacks) does the opposite.",
  revenue:
    "Revenue (sales): all the money the company took in from customers in the year, before any costs. Growing revenue shows a business " +
    "getting bigger; it says nothing yet about whether it is profitable.",
  netIncome:
    "Net income (profit): what is left of revenue after every cost, interest and tax. It can be negative (a loss). Look at its trend over " +
    "several years rather than one year alone.",
  eps:
    "Earnings per share (diluted): net income divided by the number of shares, counting those that options and convertible securities could " +
    "add. It is the profit each share earns, and what the P/E is worked out from. Rising EPS is what usually lifts a share price over time.",
  revenueGrowth:
    "How much revenue grew (or shrank) compared with the year before. Steady growth year after year is a sign of a business in demand; " +
    "compare it with the growth the P/E seems to expect.",
  netMargin:
    "Net income as a share of revenue: of every dollar of sales, how many cents the company keeps as profit. Margins differ a lot by " +
    "sector (software is often above 20%, retail a few percent), so compare with similar companies and with the company's own past.",
  priceRange:
    "The lowest and highest closing price over the period you selected, with today's price as the dot. Near the top means it trades close " +
    "to its recent highs; near the bottom, close to its lows. It shows where the price is, not whether it is cheap.",
  peRange:
    "The lowest and highest P/E over the period you selected (each day's close against the last fiscal year's EPS at the time), with " +
    "today's as the dot. A P/E near the top of its own range means investors pay more for each dollar of profit than they recently did.",
} as const;
