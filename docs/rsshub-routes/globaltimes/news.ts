import { load } from 'cheerio';
import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';

export const route: Route = {
    path: '/news',
    categories: ['government'],
    example: '/globaltimes/news',
    parameters: {},
    features: {
        requireConfig: false,
        requirePuppeteer: false,
        antiCrawler: false,
        supportBT: false,
        supportPodcast: false,
        supportScihub: false,
    },
    name: 'News (English)',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.globaltimes.cn/',
};

async function handler(): Promise<Data> {
    // Global Times 英文版首页 — 文章 URL 模式 /page/202608/1367641.shtml
    const listUrl = 'https://www.globaltimes.cn/';
    const html = await ofetch(listUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        },
        parseResponse: (t: string) => t,
    });
    const $ = load(html);

    const items = $('a[href*="/page/"]')
        .toArray()
        .map((el) => {
            const $a = $(el);
            return {
                href: $a.attr('href')?.trim() ?? '',
                title: $a.text().trim(),
            };
        })
        .filter((x) => x.href.match(/\/page\/\d{6}\/\d+\.shtml/) && x.title.length > 15);

    // 去重
    const seen = new Set<string>();
    const uniq = items.filter((x) => {
        const key = x.href;
        if (seen.has(key)) {
            return false;
        }
        seen.add(key);
        return true;
    });

    return {
        title: 'Global Times News',
        link: listUrl,
        item: uniq.map((x) => ({
            title: x.title,
            link: new URL(x.href, listUrl).toString(),
        })),
    };
}
