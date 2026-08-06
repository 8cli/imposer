import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news', categories: ['traditional-media'], example: '/newscientistfix/news',
    features: { requireConfig: false, requirePuppeteer: false, antiCrawler: false, supportBT: false, supportPodcast: false, supportScihub: false },
    name: 'News', maintainers: ['8cli'], handler, url: 'https://www.newscientist.com/feed/home',
};

async function handler(): Promise<Data> {
    const xml = await ofetch('https://www.newscientist.com/feed/home', {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        },
        parseResponse: (t: string) => t,
    });
    const feed = await parser.parseString(xml);
    return { title: feed.title ?? 'New Scientist', link: feed.link ?? 'https://www.newscientist.com/', item: feed.items.map((i) => ({ title: i.title, link: i.link, pubDate: i.pubDate, author: i.creator })) };
}
