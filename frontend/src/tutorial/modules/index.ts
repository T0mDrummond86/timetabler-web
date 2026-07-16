/** Ordered tutorial module registry. */
import type { TutorialModule } from "../types";
import { m1Orientation } from "./m1_orientation";
import { m2DataEntities } from "./m2_data_entities";
import { m3BuildTimetable } from "./m3_build_timetable";
import { m4Clashes } from "./m4_clashes";
import { m5StaffCover } from "./m5_staff_cover";
import { m6ChangelogExports } from "./m6_changelog_exports";
import { m7Capstone } from "./m7_capstone";

export const TUTORIAL_MODULES: TutorialModule[] = [
  m1Orientation,
  m2DataEntities,
  m3BuildTimetable,
  m4Clashes,
  m5StaffCover,
  m6ChangelogExports,
  m7Capstone,
];
