package com.prominence.damage.boss;
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
class BossReportFormatterTest {
 @Test void reportsEveryContributorAndGroupsUntraceableSources(){
  String report=new BossReportFormatter().format("Old Champion's Remains","defeated",List.of(new Contribution("A",60),new Contribution("B",30),new Contribution("C",10)),List.of(new Contribution("Dark Mage",5)));
  assertTrue(report.contains("1. A")); assertTrue(report.contains("2. B")); assertTrue(report.contains("3. C"));
  assertTrue(report.contains("Untraceable: Dark Mage — 5.0 damage"));
 }
}
