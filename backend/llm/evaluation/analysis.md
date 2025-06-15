# Data Source
Locally crawled news data with [crawl_news.py](../../cron/crawl_news.py) during development time. There about around 1k news entries every day. Top 5 days with most news entries as below. 

| Date | Entry Count |
| ---- | ----------- | 
| 2025-05-22 |	1098 | 
| 2025-05-15 |	1039 |
| 2025-05-20 |	1032 |
| 2025-05-21 |	1029 |
| 2025-06-10 |	1023 |

# Case Study
## **Daily news entry vs Daily Summary**  

- [news entry 05-15](news_entry_05_15.txt) vs [news summary 05-15](news_summary_05_15.txt)
- [news entry 05-20](news_entry_05_20.txt) vs [news summary 05-20](news_summary_05_20.txt)
- [news entry 05-22](news_entry_05_22.txt) vs [news summary 05-22](news_summary_05_22.txt)

## **Daily Summary vs Weekly Summary**  
Daily summary vs weekly aggregated summary from daily summary

Data:  [news summary daily week 05-19](news_summary_daily_05_19_25.txt) vs [news summary weekly week 05-19](news_summary_weekly_05_19_25.txt)

## **Summary by daily aggregate vs Summary by clustering**  
Weekly summary comparison between summary generated from daily summary and from clustering. 

Data:  [By daily aggregate week 05-19](news_summary_weekly_05_19_25.txt) vs [By clustering week 05-19](news_summary_weekly_clustering_05_19_25.txt)

## **Summary with/without user preference applied**  
**User preference:**   
"The user's interest in US national and Bay Area local news and politics (especially Trump-related news), IT tech (with a strong focus on AI breakthroughs, research, applications, investments, and ethical concerns, and the role of companies like Broadcom), international politics (East Asia, particularly China and Hong Kong, and Europe, especially Ukraine and Russia), society (generational shifts and religious sites), and the economy remains strong. The user is also interested in US border security. Prioritization should continue to be given to AI breakthroughs and research, US national and local politics, and international events in East Asia and Europe. The user prefers news summaries in bullet-point format. Rank news based on the presence of these topics and keywords, and the more specific keywords observed, like 'AI ethical concerns', 'Trump', or specific countries like 'Ukraine', 'China', 'Hong Kong', 'Russia', the higher the ranking."  

[news summary with preference 05-15](news_summary_05_15.txt) vs [news summary no preference 05-15](news_summary_no_preference_05_15.txt)  

## **Sample news research react agent working process**  
[sample news research proces](sample_news_research_process.txt)  
We can see that the agent generates multiple questions and terms to query the news entry table and provides a final summary. 


# Manual Analysis
My summarization agent does summarize news to some extent. Some summary entries are summary of multiple news entries. However many summary entries still seem too granular. Based on given user preference, my summarization agent does filter news based on user's preference. For example, the sample user prefers politics news with a strong interest in Trump. And the summary contains a lot of Trump related political summary entries comparing to the summary without user preference being applied.

Therefore my news summarization agent does much better on user preference based news filtering rather than news summarization. However, news entries are hard to summarize while pertaining useful information in the summary given the diverse and granular nature of news entries. 

Comparing the 2 aggregation algorithms' result, summary entries generated from daily summary are more consistent with user's primary preference while less diverse than summary entries generated from embedding clustering. In the above examples, summary generated from daily summary contains mainly political news while the other summary contains more IT news which is secondary user preference. 


# Future Consideration
There are 1k news entries every day. It is very hard to evaluate summarization quality manually. There are multiple alternative options. 
- Let AI evaluate summarization quality.
- Generate topic heat map from both news entries and new summary and compare the 2 heat map. 
- Ablation study. Hide different news entries in a static news entry list and compare the generated summary. The goal is to test if LLM summary could cover all news entries even if the input news entry list is as large as the LLM's context window. (1 million tokens for Gemini model) 
- Test summary of fewer new entries like 10-20. 

In the future, the summarization prompt can also be tuned to increase abstraction level of news summary maybe by adding more guidance to the prompt. 

