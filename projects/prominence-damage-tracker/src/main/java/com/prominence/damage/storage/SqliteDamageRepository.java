package com.prominence.damage.storage;

import com.prominence.damage.domain.*;
import java.nio.file.Path;
import java.sql.*;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;

public final class SqliteDamageRepository implements AutoCloseable {
    private final Connection connection;
    private boolean dirty;

    public SqliteDamageRepository(Path path) throws SQLException {
        connection = DriverManager.getConnection("jdbc:sqlite:" + path.toAbsolutePath());
        try (Statement s = connection.createStatement()) {
            s.execute("PRAGMA journal_mode=WAL");
            s.execute("PRAGMA synchronous=NORMAL");
            s.execute("PRAGMA foreign_keys=ON");
            s.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)");
            s.execute("INSERT INTO schema_version(version) SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version)");
            s.execute("CREATE TABLE IF NOT EXISTS raw_hits(id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at INTEGER NOT NULL, attacker_uuid TEXT, attacker_name TEXT, attribution_kind TEXT NOT NULL, untraceable_source_name TEXT, target_uuid TEXT NOT NULL, target_player_name TEXT, target_type_id TEXT NOT NULL, target_category TEXT NOT NULL, dimension TEXT NOT NULL, actual_damage REAL NOT NULL CHECK(actual_damage > 0), boss_session_uuid TEXT, damage_source_name TEXT NOT NULL)");
            s.execute("CREATE INDEX IF NOT EXISTS raw_hits_attacker_time ON raw_hits(attacker_uuid,occurred_at)");
            s.execute("CREATE INDEX IF NOT EXISTS raw_hits_recipient_time ON raw_hits(target_uuid,occurred_at)");
            s.execute("CREATE TABLE IF NOT EXISTS minute_aggregates(minute_epoch INTEGER NOT NULL, attacker_uuid TEXT NOT NULL, attacker_name TEXT NOT NULL, target_category TEXT NOT NULL, damage REAL NOT NULL, PRIMARY KEY(minute_epoch,attacker_uuid,target_category))");
            s.execute("CREATE TABLE IF NOT EXISTS boss_sessions(boss_entity_uuid TEXT PRIMARY KEY,boss_type_id TEXT NOT NULL,boss_display_name TEXT NOT NULL,spawned_at INTEGER NOT NULL,spawn_dimension TEXT NOT NULL,spawn_position TEXT NOT NULL,ended_at INTEGER,end_reason TEXT CHECK(end_reason IN ('death','despawn') OR end_reason IS NULL))");
        }
        connection.setAutoCommit(false);
    }

    public synchronized void record(DamageEvent e) throws SQLException {
        try (PreparedStatement p = connection.prepareStatement("INSERT INTO raw_hits(occurred_at,attacker_uuid,attacker_name,attribution_kind,untraceable_source_name,target_uuid,target_player_name,target_type_id,target_category,dimension,actual_damage,boss_session_uuid,damage_source_name) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)")) {
            int i=1; p.setLong(i++,e.occurredAt().toEpochMilli()); setUuid(p,i++,e.attackerPlayerUuid()); p.setString(i++,e.attackerLastKnownName()); p.setString(i++,e.attributionKind()); p.setString(i++,e.untraceableSourceName()); setUuid(p,i++,e.targetEntityUuid()); p.setString(i++,e.targetPlayerLastKnownName()); p.setString(i++,e.targetTypeId()); p.setString(i++,e.targetCategory().name()); p.setString(i++,e.dimension()); p.setDouble(i++,e.actualDamage()); setUuid(p,i++,e.bossSessionUuid()); p.setString(i,e.damageSourceName()); p.executeUpdate();
        }
        if (e.attackerPlayerUuid()!=null) try (PreparedStatement p = connection.prepareStatement("INSERT INTO minute_aggregates(minute_epoch,attacker_uuid,attacker_name,target_category,damage) VALUES(?,?,?,?,?) ON CONFLICT(minute_epoch,attacker_uuid,target_category) DO UPDATE SET damage=damage+excluded.damage,attacker_name=excluded.attacker_name")) {
            p.setLong(1,e.occurredAt().truncatedTo(ChronoUnit.MINUTES).getEpochSecond()); p.setString(2,e.attackerPlayerUuid().toString()); p.setString(3,Objects.requireNonNullElse(e.attackerLastKnownName(),"Unknown")); p.setString(4,e.targetCategory().name()); p.setDouble(5,e.actualDamage()); p.executeUpdate();
        }
        dirty=true;
    }

    public synchronized void flush() throws SQLException { if(dirty){connection.commit();dirty=false;} }
    public synchronized long rawEventCount() throws SQLException { try(Statement s=connection.createStatement(); ResultSet r=s.executeQuery("SELECT COUNT(*) FROM raw_hits")){return r.next()?r.getLong(1):0;} }
    public synchronized DamageTotals totalsFor(UUID player, Instant from, Instant to) throws SQLException {
        double pv=0,en=0; try(PreparedStatement p=connection.prepareStatement("SELECT target_category,SUM(actual_damage) FROM raw_hits WHERE attacker_uuid=? AND occurred_at>=? AND occurred_at<? GROUP BY target_category")){p.setString(1,player.toString());p.setLong(2,from.toEpochMilli());p.setLong(3,to.toEpochMilli());try(ResultSet r=p.executeQuery()){while(r.next()){if("PLAYER".equals(r.getString(1)))pv=r.getDouble(2);else en=r.getDouble(2);}}} return new DamageTotals(pv+en,pv,en);
    }
    public synchronized Map<UUID,DamageTotals> leaderboard(Instant from, Instant to) throws SQLException {
        Map<UUID,double[]> values=new HashMap<>(); try(PreparedStatement p=connection.prepareStatement("SELECT attacker_uuid,target_category,SUM(actual_damage) FROM raw_hits WHERE attacker_uuid IS NOT NULL AND occurred_at>=? AND occurred_at<? GROUP BY attacker_uuid,target_category")){p.setLong(1,from.toEpochMilli());p.setLong(2,to.toEpochMilli());try(ResultSet r=p.executeQuery()){while(r.next()){double[] a=values.computeIfAbsent(UUID.fromString(r.getString(1)),k->new double[2]);a["PLAYER".equals(r.getString(2))?0:1]=r.getDouble(3);}}} Map<UUID,DamageTotals> out=new HashMap<>();values.forEach((u,a)->out.put(u,new DamageTotals(a[0]+a[1],a[0],a[1])));return out;
    }
    public synchronized List<DamageEvent> damageReceivedBy(UUID recipient, Instant from, Instant to) throws SQLException {
        List<DamageEvent> out=new ArrayList<>();try(PreparedStatement p=connection.prepareStatement("SELECT occurred_at,attacker_uuid,attacker_name,attribution_kind,untraceable_source_name,target_uuid,target_player_name,target_type_id,target_category,dimension,actual_damage,boss_session_uuid,damage_source_name FROM raw_hits WHERE target_uuid=? AND occurred_at>=? AND occurred_at<? ORDER BY occurred_at")){p.setString(1,recipient.toString());p.setLong(2,from.toEpochMilli());p.setLong(3,to.toEpochMilli());try(ResultSet r=p.executeQuery()){while(r.next())out.add(readEvent(r));}}return out;
    }
    public synchronized Map<UUID,Double> contributionsForSession(UUID bossSessionUuid) throws SQLException {
        Map<UUID,Double> out=new HashMap<>();
        try(PreparedStatement p=connection.prepareStatement("SELECT attacker_uuid,SUM(actual_damage) FROM raw_hits WHERE boss_session_uuid=? AND attacker_uuid IS NOT NULL GROUP BY attacker_uuid")){
            p.setString(1,bossSessionUuid.toString());
            try(ResultSet r=p.executeQuery()){while(r.next())out.put(UUID.fromString(r.getString(1)),r.getDouble(2));}
        }
        return out;
    }

    /**
     * Most-recent known name for every player who contributed to a boss session.
     * Used to restore the display-name cache after a restart so pre-restart
     * contributors are not shown as raw UUID prefixes.
     */
    public synchronized Map<UUID,String> contributorNamesForSession(UUID bossSessionUuid) throws SQLException {
        Map<UUID,String> out=new HashMap<>();
        String sql="SELECT attacker_uuid, (SELECT attacker_name FROM raw_hits h2 WHERE h2.attacker_uuid=h1.attacker_uuid AND h2.attacker_name IS NOT NULL ORDER BY occurred_at DESC LIMIT 1) AS latest_name"
                + " FROM raw_hits h1 WHERE boss_session_uuid=? AND attacker_uuid IS NOT NULL GROUP BY attacker_uuid";
        try(PreparedStatement p=connection.prepareStatement(sql)){
            p.setString(1,bossSessionUuid.toString());
            try(ResultSet r=p.executeQuery()){while(r.next()){String n=r.getString(2); if(n!=null) out.put(UUID.fromString(r.getString(1)),n);}}
        }
        return out;
    }

    public record LeaderRow(UUID uuid, String name, double total, double toPlayers, double toEntities) {}

    /**
     * Per-player damage leaderboard over a time window, split by target category,
     * using each player's most-recent known name. Backs the private
     * {@code /pdamage <minutes>} leaderboard form.
     */
    public synchronized List<LeaderRow> windowLeaderboard(Instant from, Instant to, int limit) throws SQLException {
        String sql =
            "SELECT attacker_uuid," +
            " SUM(CASE WHEN target_category='PLAYER' THEN actual_damage ELSE 0 END) AS pv," +
            " SUM(CASE WHEN target_category='ENTITY' THEN actual_damage ELSE 0 END) AS en," +
            " SUM(actual_damage) AS tot," +
            " (SELECT attacker_name FROM raw_hits h2 WHERE h2.attacker_uuid=h1.attacker_uuid AND h2.attacker_name IS NOT NULL ORDER BY occurred_at DESC LIMIT 1) AS latest_name" +
            " FROM raw_hits h1 WHERE attacker_uuid IS NOT NULL AND occurred_at>=? AND occurred_at<?" +
            " GROUP BY attacker_uuid ORDER BY tot DESC LIMIT ?";
        List<LeaderRow> out = new ArrayList<>();
        try (PreparedStatement p = connection.prepareStatement(sql)) {
            p.setLong(1, from.toEpochMilli());
            p.setLong(2, to.toEpochMilli());
            p.setInt(3, limit);
            try (ResultSet r = p.executeQuery()) {
                while (r.next()) {
                    out.add(new LeaderRow(UUID.fromString(r.getString("attacker_uuid")),
                            r.getString("latest_name"), r.getDouble("tot"),
                            r.getDouble("pv"), r.getDouble("en")));
                }
            }
        }
        return out;
    }

    public synchronized List<LeaderRow> lifetimeLeaderboard(int limit) throws SQLException {
        // Sum per attacker across all time, split by category, using the most recent known name.
        String sql =
            "SELECT attacker_uuid," +
            " SUM(CASE WHEN target_category='PLAYER' THEN actual_damage ELSE 0 END) AS pv," +
            " SUM(CASE WHEN target_category='ENTITY' THEN actual_damage ELSE 0 END) AS en," +
            " SUM(actual_damage) AS tot," +
            " (SELECT attacker_name FROM raw_hits h2 WHERE h2.attacker_uuid=h1.attacker_uuid AND h2.attacker_name IS NOT NULL ORDER BY occurred_at DESC LIMIT 1) AS latest_name" +
            " FROM raw_hits h1 WHERE attacker_uuid IS NOT NULL" +
            " GROUP BY attacker_uuid ORDER BY tot DESC LIMIT ?";
        List<LeaderRow> out = new ArrayList<>();
        try (PreparedStatement p = connection.prepareStatement(sql)) {
            p.setInt(1, limit);
            try (ResultSet r = p.executeQuery()) {
                while (r.next()) {
                    out.add(new LeaderRow(UUID.fromString(r.getString("attacker_uuid")),
                            r.getString("latest_name"), r.getDouble("tot"),
                            r.getDouble("pv"), r.getDouble("en")));
                }
            }
        }
        return out;
    }

    /** Total damage dealt to a boss session that could NOT be attributed to any player. */
    public synchronized double unattributedForSession(UUID bossSessionUuid) throws SQLException {
        try (PreparedStatement p = connection.prepareStatement(
                "SELECT COALESCE(SUM(actual_damage),0) FROM raw_hits WHERE boss_session_uuid=? AND attacker_uuid IS NULL")) {
            p.setString(1, bossSessionUuid.toString());
            try (ResultSet r = p.executeQuery()) { return r.next() ? r.getDouble(1) : 0.0; }
        }
    }

    public synchronized void openBossSession(BossSession s) throws SQLException { try(PreparedStatement p=connection.prepareStatement("INSERT OR IGNORE INTO boss_sessions(boss_entity_uuid,boss_type_id,boss_display_name,spawned_at,spawn_dimension,spawn_position,ended_at,end_reason) VALUES(?,?,?,?,?,?,?,?)")){p.setString(1,s.bossEntityUuid().toString());p.setString(2,s.bossTypeId());p.setString(3,s.bossDisplayName());p.setLong(4,s.spawnedAt().toEpochMilli());p.setString(5,s.spawnDimension());p.setString(6,s.spawnPosition());if(s.endedAt()==null)p.setNull(7,Types.BIGINT);else p.setLong(7,s.endedAt().toEpochMilli());p.setString(8,s.endReason());p.executeUpdate();dirty=true;} }
    public synchronized void closeBossSession(UUID id,Instant ended,String reason)throws SQLException{if(!reason.equals("death")&&!reason.equals("despawn"))throw new IllegalArgumentException("invalid end reason");try(PreparedStatement p=connection.prepareStatement("UPDATE boss_sessions SET ended_at=?,end_reason=? WHERE boss_entity_uuid=? AND ended_at IS NULL")){p.setLong(1,ended.toEpochMilli());p.setString(2,reason);p.setString(3,id.toString());p.executeUpdate();dirty=true;}}
    public synchronized List<BossSession> activeBossSessions()throws SQLException{List<BossSession> out=new ArrayList<>();try(Statement s=connection.createStatement();ResultSet r=s.executeQuery("SELECT boss_entity_uuid,boss_type_id,boss_display_name,spawned_at,spawn_dimension,spawn_position,ended_at,end_reason FROM boss_sessions WHERE ended_at IS NULL ORDER BY spawned_at")){while(r.next())out.add(readSession(r));}return out;}
    public synchronized Optional<BossSession> bossSession(UUID id)throws SQLException{try(PreparedStatement p=connection.prepareStatement("SELECT boss_entity_uuid,boss_type_id,boss_display_name,spawned_at,spawn_dimension,spawn_position,ended_at,end_reason FROM boss_sessions WHERE boss_entity_uuid=?")){p.setString(1,id.toString());try(ResultSet r=p.executeQuery()){return r.next()?Optional.of(readSession(r)):Optional.empty();}}}
    private static BossSession readSession(ResultSet r)throws SQLException{long end=r.getLong(7);return new BossSession(UUID.fromString(r.getString(1)),r.getString(2),r.getString(3),Instant.ofEpochMilli(r.getLong(4)),r.getString(5),r.getString(6),r.wasNull()?null:Instant.ofEpochMilli(end),r.getString(8));}
    private static DamageEvent readEvent(ResultSet r)throws SQLException{return new DamageEvent(Instant.ofEpochMilli(r.getLong(1)),uuid(r.getString(2)),r.getString(3),r.getString(4),r.getString(5),UUID.fromString(r.getString(6)),r.getString(7),r.getString(8),TargetCategory.valueOf(r.getString(9)),r.getString(10),r.getDouble(11),uuid(r.getString(12)),r.getString(13));}
    private static UUID uuid(String s){return s==null?null:UUID.fromString(s);} private static void setUuid(PreparedStatement p,int i,UUID u)throws SQLException{p.setString(i,u==null?null:u.toString());}
    @Override public synchronized void close() throws SQLException { flush(); connection.close(); }
}
