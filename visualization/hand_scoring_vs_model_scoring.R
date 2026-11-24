# comparison of handscoring results to model scoring results
# Lucas Watson


# load libraries ----------------------------------------------------------

# loading data and tidying
library(tidyverse)
library(here)
library(readxl)
library(janitor)

# analysis
library(psych)

# load data ---------------------------------------------------------------

# hand scoring data
hand_scored <- read_xlsx(here('hand_scored', 'summer_hand_scored.xlsx'))

# gpt5.0 default reasoning
default_scored <- read_csv(here('model_output', 'default_scoring_long.csv'))

# gpt5.0 low effort reasoning
low_effort_scored <- read_csv(here('model_output', 'low-effort_scoring_long.csv'))

# cleaning ----------------------------------------------------------------

# remove label columns and total rows, keeping only eventID, # details recalled
# for objects, actions, person/character, locations, and goals
default_scored_clean <- default_scored |> 
  select(Session:EventID, ends_with('Count'), EventRemembered_0_1) |> 
  select(!contains('Details')) |> 
  filter(!str_detect(EventID, 'TOTAL') & !is.na(EventID)) |> 
  mutate(
    CoderID = 'gpt-5.0-default', 
    EventID = as.numeric(EventID)
  )

low_effort_scored_clean <- low_effort_scored |> 
  select(Session:EventID, ends_with('Count'), EventRemembered_0_1) |> 
  select(!contains('Details')) |> 
  filter(!str_detect(EventID, 'TOTAL') & !is.na(EventID)) |> 
  mutate(
    CoderID = 'gpt-5.0-low-effort', 
    EventID = as.numeric(EventID)
  )

# make the colnames same across tables, prepare for joining

# rename total to count in handscored
colnames(hand_scored) <- str_replace(colnames(hand_scored), 'Total', 'Count')

# add coder id to hand scored
hand_scored_clean <- hand_scored |> 
  mutate(
    CoderID = 'hand-scored'
  ) |> 
  rename(EventID = Event)

# bind dfs together hamburger style
scores <- hand_scored_clean |> 
  bind_rows(low_effort_scored_clean, default_scored_clean)


# interrater reliability --------------------------------------------------

# find out how much these raters agree on scoring event recall across events, 
# categories, and participants

# find total IRR with intraclass correlation coeff. (ICC)

# summarize by rater and participant, pivot
wide_totals <- scores |> 
  group_by(CoderID, ParticipantID) |> 
  summarize(
    across(ends_with('Count'), \(x) sum(x, na.rm = T))
  ) |> 
  ungroup() |> 
  select(-starts_with('G')) |> 
  pivot_longer(
    ends_with('Count'), 
    names_to = 'Category', 
    values_to = 'Count'
  ) |> 
  group_by(CoderID, ParticipantID) |> 
  summarize(
    total = sum(Count)
  ) |> 
  pivot_wider(
    names_from = CoderID, 
    values_from = total
  ) |> 
  ungroup()

colnames(wide_totals) <- make_clean_names(colnames(wide_totals))

# compute ICC benchmarked against human rater
def_hum <- ICC(wide_totals[, c(2, 4)])

# look to ICC2 as generalizable reliability metric to future AI/human comps
def_hum$results

# default AI has non-significant agreement with human rater, ICC3 is higher, 
# indicating that inconsistency may be stemming from conservative bias

# low effort
low_hum <- ICC(wide_totals[, c(3, 4)])

# look to ICC2 as generalizable reliability metric to future AI/human comps
low_hum$results

# low effort has significant positive agreement with human rater

# could be possible that default reasoning is more strict, or aligns with 
# novice human rater more? 

summary(wide_totals$gpt_5_0_default - wide_totals$hand_scored)
summary(wide_totals$gpt_5_0_low_effort - wide_totals$hand_scored)

# both seem to undercount details relative to the human scorer, but low effort
# model undercounted less often


# ICC by event ------------------------------------------------------------

# conduct ICC analysis by event across raters and participants
wide_totals <- scores |> 
  group_by(CoderID, ParticipantID, EventID) |> 
  summarize(
    across(ends_with('Count'), \(x) sum(x, na.rm = T))
  ) |> 
  ungroup() |> 
  select(-starts_with('G')) |> 
  pivot_longer(
    ends_with('Count'), 
    names_to = 'Category', 
    values_to = 'Count'
  ) |> 
  group_by(CoderID, ParticipantID, EventID) |> 
  summarize(
    total = sum(Count)
  ) |> 
  pivot_wider(
    names_from = CoderID, 
    values_from = total
  ) |> 
  ungroup()

colnames(wide_totals) <- make_clean_names(colnames(wide_totals))

# helper icc function
get_event_icc <- function(df_sub, rater_cols) {
  res <- ICC(df_sub[, rater_cols], lmer = FALSE)$results
  
  tibble(
    ICC2 = res["Single_random_raters", "ICC"],
    ICC2_p = res["Single_random_raters", "p"],
    ICC3 = res["Single_fixed_raters", "ICC"],
    ICC3_p = res["Single_fixed_raters", "p"],
    Mean_Diff = mean(df_sub[[rater_cols[2]]] - df_sub[[rater_cols[1]]], na.rm = TRUE)
  )
}

# calculate by-event ICC
by_event_results_default <- wide_totals |> 
  group_by(event_id) |> 
  group_modify(~ get_event_icc(.x, c('hand_scored', 'gpt_5_0_default'))) |> 
  ungroup()

by_event_results_default

# plot the # details recalled by model for visual comparison of agreement by events

# appears that events 2 and 4 are most ambiguous and lead to largest difference 
# between human and default model

by_event_results_low_effort <- wide_totals |> 
  group_by(event_id) |> 
  group_modify(~ get_event_icc(.x, c('hand_scored', 'gpt_5_0_low_effort'))) |> 
  ungroup()

by_event_results_low_effort

# same for low effort! I think that some of this could be coming from some poor
# or overlapping event definitions. these tripped me up a bit, and I would often 
# give the person the benefit of the doubt

# plots will help show true detail discrepancies between human and models

# visualization -----------------------------------------------------------

fp_theme <- function() {
  theme_bw() + 
    theme(
      text = element_text(family = 'Aptos', size = 14),
      title = element_text(family = 'Aptos', face = 'bold', size = 16),
      panel.grid.major.x = element_blank(),
      panel.grid.minor = element_blank(), 
      strip.background = element_rect(color = 'black', fill = 'black'), 
      strip.text = element_text(color = 'white', face = 'bold')
    )
}

library(showtext)

font_add('Aptos', regular = 'Aptos.ttf', bold = 'Aptos-bold.ttf')

showtext_opts(dpi = 300)
showtext_auto()

segments <- wide_totals |> 
  pivot_longer(
    starts_with('gpt'), 
    names_to = 'rater', 
    values_to = 'count'
  )

wide_totals |> 
  pivot_longer(
    gpt_5_0_default:hand_scored, 
    names_to = 'rater', 
    values_to = 'count'
  ) |> 
  ggplot() +
  geom_segment(
    data = segments, 
    aes(x = hand_scored, xend = count, y = event_id, color = factor(rater)), 
    linewidth = .75
  ) +
  geom_point(
    aes(x = count, y = event_id, color = factor(rater), shape = factor(rater)), 
    size = 2
  ) + 
  scale_x_continuous(
    'Details recalled',
    breaks = seq(0, 10), limits = c(0, 10)
  ) +
  scale_y_continuous(
    'Event', 
    breaks = seq(1, 9), limits = c(1, 9)
  ) +
  scale_color_manual(
    'Rater',
    labels = c('Default GPT-5.0', 'Low effort GPT-5.0', 'Human'),
    values = c('firebrick4', 'pink3', 'black')
  ) +
  scale_shape_manual(
    'Rater', 
    labels = c('Default GPT-5.0', 'Low effort GPT-5.0', 'Human'),
    values = c(17, 17, 19)
  ) +
  facet_wrap(~participant_id) +
  fp_theme()

# save
ggsave(
  here('fig_output', 'details_recalled_by_event.png'), device = 'png', 
  dpi = 300, width = 8, height = 4.5, units = 'in'
)

# totals
segments <- wide_totals |> 
  group_by(participant_id) |> 
  summarize(
    across(gpt_5_0_default:hand_scored, sum)
  ) |> 
  pivot_longer(
    starts_with('gpt'), 
    names_to = 'rater', 
    values_to = 'count'
  ) |> 
  mutate(y = 1)

wide_totals |> 
  pivot_longer(
    gpt_5_0_default:hand_scored, 
    names_to = 'rater', 
    values_to = 'count'
  ) |> 
  group_by(participant_id, rater) |> 
  summarize(
    count = sum(count), 
    y = 1
  ) |> 
  ggplot() +
  geom_segment(
    data = segments, 
    aes(x = hand_scored, xend = count, y = y, color = factor(rater)), 
    linewidth = .75
  ) +
  geom_point(
    aes(x = count, y = y, color = factor(rater), shape = factor(rater)), 
    size = 2
  ) + 
  scale_x_continuous(
    'Details recalled',
    breaks = seq(0, 60, 10), limits = c(0, 60)
  ) +
  scale_y_continuous('', breaks = c(1), labels = NULL, expand = c(0, 0)) +
  scale_color_manual(
    'Rater',
    labels = c('Default GPT-5.0', 'Low effort GPT-5.0', 'Human'),
    values = c('firebrick4', 'pink3', 'black')
  ) +
  scale_shape_manual(
    'Rater',
    labels = c('Default GPT-5.0', 'Low effort GPT-5.0', 'Human'),
    values = c(17, 17, 19)
  ) +
  facet_wrap(~participant_id) +
  fp_theme()

# save
ggsave(
  here('fig_output', 'total_details_recalled.png'), device = 'png', 
  dpi = 300, width = 8, height = 2, units = 'in'
)
