use 5.10.0;
use strict;
use warnings;

package TestMe;
use Test::More;
use lib './lib';
use Seq::Tracks::Build;
use Try::Tiny;
use DDP;

use Seq::Output::Delimiters;

my $delims = Seq::Output::Delimiters->new();

my $line = "Stuff;1;2;3\\4\t5/6|7";

my $expected = "Stuff 1 2 3 4\t5 6 7";

$delims->cleanDelims->($line);

ok($line eq $expected, "Clean all delimiters, even backslash");

my @parts = split('\t', $line);

ok(@parts == 2, "Splitting on single quoted tab char ('\\t') still works");

my @parts2 = split("\t", $line);
ok(@parts == 2, "Splitting on double quoted tab char (\"\\t\") still works");

$line = "Stuff;;1;;2;;;3\\\\4\t5//6||7|";

$expected = "Stuff 1 2 3 4\t5 6 7 ";

$delims->cleanDelims->($line);

ok($line eq $expected, "Clean all delimiters even when many instances in a row");

@parts = split('\t', $line);

ok(@parts == 2, "Splitting on single quoted tab char ('\\t') still works");

@parts2 = split("\t", $line);
ok(@parts == 2, "Splitting on double quoted tab char (\"\\t\") still works");

done_testing();